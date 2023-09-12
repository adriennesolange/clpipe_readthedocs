"""Postprocessing Pipeline Workflow Builder and Distributer.

Based on user input, builds and runs a postprocessing pipeline for a set 
of subjects, distributing the workload across a cluster if requested.
"""

import sys
import os
import warnings
import json
import time
from pathlib import Path

from .bids import (
    get_bids,
    get_confounds,
    get_images_to_process,
    get_mask,
    get_mixing_file,
    get_noise_file,
    get_subjects,
    get_tr,
    validate_subject_exists,
)
import nipype.pipeline.engine as pe
import pydantic

# This hides a pybids future warning
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=FutureWarning)
    from bids import BIDSLayout
    from bids.layout import BIDSFile

from .config.options import ProjectOptions, PostProcessingRunConfig
from .config.options import DEFAULT_PROCESSING_STREAM
from .batch_manager import BatchManager, Job
from .postprocutils.global_workflows import build_postprocessing_wf
from .postprocutils.utils import draw_graph
from .utils import get_logger, resolve_fmriprep_dir
from .errors import *

STEP_NAME = "postprocess"
PROCESSING_DESCRIPTION_FILE_NAME = "processing_description.json"
IMAGE_TIME_DIMENSION_INDEX = 3
IMAGE_SUBMISSION_STRING_TEMPLATE = (
    "postprocess_image {config_file} "
    "{image_path} {bids_dir} {fmriprep_dir} {pybids_db_path} {out_dir} "
    "{subject_out_dir} {processing_stream} {subject_working_dir} {log_dir} "
    "{debug}"
)
SUBJECT_SUBMISSION_STRING_TEMPLATE = (
    "postprocess_subject {subject_id} {bids_dir} {fmriprep_dir} {output_dir} "
    "{processing_stream} {config_file} {index_dir} {log_dir} {batch} {submit} "
    "{debug}"
)
BIDS_INDEX_NAME = "bids_index"
"""This is the location of the pybids-generated index"""

SUBJECT_LOG_DIR = "distributor"
"""Where to save batch files, within the postprocessing log folder, for subject-level batch logs"""
RUN_CONFIG_FILE_NAME = "run_config.json"

def postprocess_subjects(
    subjects=None,
    config_file=None,
    bids_dir=None,
    fmriprep_dir=None,
    output_dir=None,
    processing_stream=DEFAULT_PROCESSING_STREAM,
    batch=False,
    submit=False,
    log_dir=None,
    pybids_db_path=None,
    refresh_index=False,
    debug=False,
    cache=True,
):
    """
    Parse configuration and sanitize inputs in preparation for
        subject job distribution.
    """

    options: ProjectOptions = ProjectOptions.load(config_file)
    options.fmriprep.load_cli_args(
        bids_directory = bids_dir,
    )
    options.postprocessing.load_cli_args(
        output_directory = output_dir,
        target_directory = fmriprep_dir
    )

    # Initialize the run config
    run_config: PostProcessingRunConfig = PostProcessingRunConfig(
        options = options.postprocessing,
        stream_working_dir = options.postprocessing.get_stream_working_dir(processing_stream),
        stream_log_dir = options.postprocessing.get_stream_log_dir(processing_stream),
        stream_output_dir = options.postprocessing.get_stream_output_dir(processing_stream),
        pybids_db_path = options.postprocessing.get_pybids_db_path(processing_stream, BIDS_INDEX_NAME)
    )
    run_config.load_cli_args(
        pybids_db_path = pybids_db_path
    )

    setup_dirs(run_config)
    run_config.dump(Path(run_config.stream_working_dir) / RUN_CONFIG_FILE_NAME)

    # Setup Logging
    logger= get_logger(STEP_NAME, debug=debug, log_dir=options.get_logs_dir())

    options.postprocessing.target_directory = resolve_fmriprep_dir(options.postprocessing.target_directory)
    logger.info(f"Preparing postprocessing job targeting: {options.postprocessing.target_directory}")
    
    time.sleep(0.5)

    logger.info(f"Output directory: {options.postprocessing.output_directory}")

    # Check to make sure working directory has been changed from the default
    if options.postprocessing.working_directory == ProjectOptions().postprocessing.working_directory:
        logger.error("A working directory for this step must be provided in your config file.")
        sys.exit(1)

    # Setup batch jobs if indicated
    batch_manager = None
    if batch:
        slurm_log_dir = log_dir / SUBJECT_LOG_DIR
        slurm_log_dir = os.path.join(
            log_dir, SUBJECT_LOG_DIR
        )
        os.makedirs(slurm_log_dir, exist_ok=True)
    
        batch_manager: BatchManager = _setup_batch_manager(options, non_processing=True)

    

    # Create jobs based on subjects given for processing
    try:
        bids: BIDSLayout = get_bids(
            options.fmriprep.bids_directory,
            database_path=run_config.pybids_db_path,
            logger=logger,
            fmriprep_dir=options.postprocessing.target_directory,
            refresh=refresh_index,
        )

        subjects_to_process = get_subjects(bids, subjects)
        logger.info(
            f"Processing requested for subject(s): {','.join(subjects_to_process)}"
        )
        time.sleep(0.5)

        logger.info("Creating submission string(s)")
        submission_strings = {}
        time.sleep(0.5)

        batch_flag = "" if batch_manager else "-no-batch"
        submit_flag = "-submit" if submit else ""
        debug_flag = "-debug" if debug else ""

        for subject in subjects_to_process:
            key = "Postprocessing_sub-" + subject
            submission_strings[key] = SUBJECT_SUBMISSION_STRING_TEMPLATE.format(
                subject_id=subject,
                bids_dir=options.fmriprep.bids_directory,
                fmriprep_dir=options.postprocessing.target_directory,
                config_file=config_file,
                index_dir=run_config.pybids_db_path,
                output_dir=options.postprocessing.target_directory,
                processing_stream=processing_stream,
                log_dir=options.postprocessing.log_directory,
                batch=batch_flag,
                submit=submit_flag,
                debug=debug_flag,
            )

        _submit_jobs(batch_manager, submission_strings, logger, submit=submit)
    except NoSubjectsFoundError as nsfe:
        logger.error(nsfe)
        sys.exit(1)
    except FileNotFoundError as fnfe:
        logger.error(fnfe)
        sys.exit(1)

def setup_dirs(run_config: PostProcessingRunConfig):
    os.makedirs(run_config.stream_output_dir, exist_ok=True)
    os.makedirs(run_config.stream_working_dir, exist_ok=True)
    os.makedirs(run_config.stream_log_dir, exist_ok=True)

def postprocess_subject(
    subject_id,
    bids_dir,
    fmriprep_dir,
    output_dir,
    config_file,
    index_dir,
    batch,
    submit,
    log_dir,
    processing_stream=DEFAULT_PROCESSING_STREAM,
    debug=False,
):
    """
    Parse configuration and (TODO) sanitize inputs for image job distribution.
    """

    logger = get_logger("postprocess_subject", debug=debug)
    logger.info(f"Processing subject: {subject_id}")

    # Create a postprocessing logging directory for this subject,
    # if it doesn't exist
    log_dir: Path = Path(log_dir) / ("sub-" + subject_id)
    log_dir.mkdir(exist_ok=True)

    config: ProjectOptions = ProjectOptions.load(config_file)

    config.get = Path(output_dir) / processing_stream
    postprocessing_config = _fetch_postprocessing_stream_config(
        config, config.postprocessing.get_stream_dir(), processing_stream=processing_stream
    )

    batch_manager = None
    if batch:
        batch_manager = _setup_batch_manager(config, log_dir)

    try:
        bids: BIDSLayout = get_bids(
            bids_dir, database_path=index_dir, fmriprep_dir=fmriprep_dir
        )
        validate_subject_exists(bids, subject_id, logger)

        image_space = postprocessing_config["TargetImageSpace"]
        try:
            tasks = postprocessing_config["TargetTasks"]
        except KeyError:
            logger.warn(
                (
                    "Postprocessing configuration setting 'TargetTasks' not set. "
                    "Defaulting to all tasks."
                )
            )
            tasks = None
        try:
            acquisitions = postprocessing_config["TargetAcquisitions"]
        except KeyError:
            logger.warn(
                (
                    "Postprocessing configuration setting 'TargetAcquisitions' "
                    "not set. Defaulting to all acquisitions."
                )
            )
            acquisitions = None

        images_to_process = get_images_to_process(
            subject_id,
            image_space,
            bids,
            logger,
            tasks=tasks,
            acquisitions=acquisitions,
        )

        subject_out_dir = output_dir / processing_stream / ("sub-" + subject_id)

        working_dir = postprocessing_config["WorkingDirectory"]
        subject_working_dir = _get_subject_working_dir(
            working_dir, output_dir, subject_id, processing_stream
        )

        if not subject_out_dir.exists():
            logger.info(f"Creating subject directory: {subject_out_dir}")
            subject_out_dir.mkdir(parents=True)

        if not subject_working_dir.exists():
            logger.info(f"Creating subject working directory: {subject_working_dir}")
            subject_working_dir.mkdir(parents=True, exist_ok=False)

        submission_strings = _create_image_submission_strings(
            images_to_process,
            bids_dir,
            fmriprep_dir,
            index_dir,
            output_dir,
            subject_out_dir,
            processing_stream,
            subject_working_dir,
            config_file,
            log_dir,
            debug,
            logger,
        )

        _submit_jobs(batch_manager, submission_strings, logger, submit=submit)
    except SubjectNotFoundError as snfe:
        logger.error(snfe)
        sys.exit()
    except ValueError as ve:
        logger.error(ve)
        sys.exit()
    except FileNotFoundError as fnfe:
        logger.error(fnfe)
        sys.exit()

    sys.exit()


def postprocess_image(
    config_file,
    image_path,
    bids_dir,
    fmriprep_dir,
    pybids_db_path,
    out_dir,
    subject_out_dir,
    subject_working_dir,
    log_dir,
    processing_stream=DEFAULT_PROCESSING_STREAM,
    confounds_only=False,
    debug=False,
):
    """
    Setup the workflows specified in the postprocessing configuration.
    """

    logger = get_logger("postprocess_image", debug=debug)
    logger.info(f"Processing image: {image_path}")

    config = _parse_config(config_file)
    config_file = Path(config_file)

    stream_output_dir = Path(out_dir) / processing_stream
    postprocessing_config = _fetch_postprocessing_stream_config(
        config, stream_output_dir, processing_stream=processing_stream
    )

    image_path = Path(image_path)
    subject_working_dir = Path(subject_working_dir)
    log_dir = Path(log_dir)
    subject_out_dir = Path(subject_out_dir)

    # Grab only the image file name in a way that works
    #   on both .nii and .nii.gz
    file_name_no_extensions = Path(
        str(image_path).rstrip("".join(image_path.suffixes))
    ).stem
    # Remove modality to shorten necessary pipeline name
    file_name_no_modality = file_name_no_extensions.replace("_desc-preproc_bold", "")
    # Remove hyphens to allow use as a pipeline name
    pipeline_name = file_name_no_modality.replace("-", "_")

    bids: BIDSLayout = get_bids(
        bids_dir, database_path=pybids_db_path, fmriprep_dir=fmriprep_dir
    )
    # Lookup the BIDSFile with the image path
    bids_image: BIDSFile = bids.get_file(image_path)
    # Fetch the image's entities
    image_entities = bids_image.get_entities()
    # Create a sub dict of the entities we will need to query on
    query_params = {
        k: image_entities[k]
        for k in image_entities.keys()
        & {"session", "subject", "task", "run", "acquisition", "space"}
    }
    # Create a specific dict for searching non-image files
    non_image_query_params = query_params.copy()
    non_image_query_params.pop("space")

    mixing_file, noise_file = None, None
    if "AROMARegression" in postprocessing_config["ProcessingSteps"]:
        try:
            # TODO: update these for image entities
            mixing_file = get_mixing_file(bids, non_image_query_params, logger)
            noise_file = get_noise_file(bids, non_image_query_params, logger)
        except MixingFileNotFoundError as mfnfe:
            logger.error(mfnfe)
            # TODO: this should raise the error for the controller to handle
            sys.exit(1)
        except NoiseFileNotFoundError as nfnfe:
            logger.error(nfnfe)
            sys.exit(1)

    # Search for this subject's files necessary for processing
    mask_image = get_mask(bids, query_params, logger)
    tr = get_tr(bids, query_params, logger)
    confounds_path = get_confounds(bids, non_image_query_params, logger)

    # Try and build an export path for postprocess confounds if the subject has
    #   confounds to work with
    confounds_export_path = None
    if confounds_path is not None:
        try:
            confounds_export_path = build_export_path(
                confounds_path, query_params["subject"], fmriprep_dir, subject_out_dir
            )
        except ValueError as ve:
            logger.warn(ve)
            logger.warn("Skipping confounds processing")

    # Build the image export path
    image_export_path = None
    if not confounds_only:
        image_export_path = build_export_path(
            image_path, query_params["subject"], fmriprep_dir, subject_out_dir
        )

    # Build the global postprocessing workflow
    postproc_wf: pe.Workflow = build_postprocessing_wf(
        postprocessing_config,
        tr,
        name=pipeline_name,
        image_file=bids_image,
        image_export_path=image_export_path,
        confounds_file=confounds_path,
        confounds_export_path=confounds_export_path,
        working_dir=subject_working_dir,
        mask_file=mask_image,
        mixing_file=mixing_file,
        noise_file=noise_file,
        base_dir=subject_working_dir,
        crashdump_dir=log_dir,
    )

    if postprocessing_config["WriteProcessGraph"]:
        draw_graph(postproc_wf, "processing_graph", stream_output_dir, logger=logger)

    postproc_wf.run()
    sys.exit(0)

def build_export_path(
    image_path: os.PathLike,
    subject_id: str,
    fmriprep_dir: os.PathLike,
    subject_out_dir: os.PathLike,
) -> Path:
    """Builds a new name for a processed image.

    Args:
        image_path (os.PathLike): The path to the original image file.
        subject_out_dir (os.PathLike): The destination directory.

    Returns:
        os.PathLike: Save path for an image file.
    """
    # Copy the directory structure following the subject-id
    # from the fmriprep dir
    out_path = Path(image_path).relative_to(Path(fmriprep_dir) / ("sub-" + subject_id))
    export_path = Path(subject_out_dir) / str(out_path)
    export_folder = export_path.parent

    # Create the output folder if it doesn't exist
    if not export_folder.exists():
        export_folder.mkdir(parents=True, exist_ok=True)

    export_path = Path(subject_out_dir) / str(out_path).replace("preproc", "postproc")
    print(f"Export path: {export_path}")

    return export_path


def _fetch_postprocessing_stream_config(
    config: dict,
    stream_output_dir: os.PathLike,
    processing_stream: str = DEFAULT_PROCESSING_STREAM,
):
    """
    The postprocessing stream config is a subset of the main
    configuration's postprocessing config, based on
    selections made in the processing streams config.

    This stream postprocessing config is saved as a seperate configuration
    file at the level of the output folder / stream folder and
    is referred to by the workflow builders.
    """

    postprocessing_description_file = (
        Path(stream_output_dir) / PROCESSING_DESCRIPTION_FILE_NAME
    )
    postprocessing_config = _postprocessing_config_apply_processing_stream(
        config, processing_stream=processing_stream
    )
    _write_processing_description_file(
        postprocessing_config, postprocessing_description_file
    )

    return postprocessing_config


def _list_available_streams(postprocessing_config: dict):
    return postprocessing_config.keys()


def _write_processing_description_file(
    postprocessing_config: dict, processing_description_file: os.PathLike
):
    processing_steps = postprocessing_config["ProcessingSteps"]
    processing_step_options = postprocessing_config["ProcessingStepOptions"]
    processing_step_options_reference = processing_step_options.copy()
    confound_options = postprocessing_config["ConfoundOptions"]

    # Remove processing options not used
    for step_option in processing_step_options_reference.keys():
        if step_option not in processing_steps:
            processing_step_options.pop(step_option)

    # Write the processing file
    with open(processing_description_file, "w") as file_to_write:
        json.dump(postprocessing_config, file_to_write, indent=4)


def _postprocessing_config_apply_processing_stream(
    config: dict, processing_stream: str = DEFAULT_PROCESSING_STREAM
):
    postprocessing_config = _get_postprocessing_config(config)
    processing_streams = _get_processing_streams(config)

    # If using the default stream, no need to update postprocessing config
    if processing_stream == DEFAULT_PROCESSING_STREAM:
        return postprocessing_config

    # Iterate through the available processing streams and see
    #   if one matches the one requested
    # The default processing stream name won't be in this list -
    #   it refers to the base PostProcessingOptions
    for stream in processing_streams:
        stream_options = stream["PostProcessingOptions"]

        if stream["ProcessingStream"] == processing_stream:
            # Use deep update to impart the processing stream options
            #   into the postprocessing config
            postprocessing_config = pydantic.utils.deep_update(
                postprocessing_config, stream_options
            )
            return postprocessing_config

    raise ValueError(f"No stream found in configuration with name: {processing_stream}")


def _get_postprocessing_config(config: dict):
    return config["PostProcessingOptions2"]


def _get_processing_streams(config: dict):
    return config["ProcessingStreams"]


def _submit_jobs(batch_manager, submission_strings, logger, submit=True):
    num_jobs = len(submission_strings)

    if batch_manager:
        _populate_batch_manager(batch_manager, submission_strings, logger)
        if submit:
            batch_manager.submit_jobs()
        else:
            batch_manager.print_jobs()
    else:
        if submit:
            for key in submission_strings.keys():
                os.system(submission_strings[key])
        else:
            for key in submission_strings.keys():
                print(submission_strings[key])


def _create_image_submission_strings(
    images_to_process,
    bids_dir,
    fmriprep_dir,
    pybids_db_path,
    out_dir,
    subject_out_dir,
    processing_stream,
    subject_working_dir,
    config_file,
    log_dir,
    debug,
    logger,
):
    logger.info(f"Building image job submission strings")
    submission_strings = {}

    debug_flag = ""
    if debug:
        debug_flag = "-debug"

    logger.info("Creating submission string(s)")
    for image in images_to_process:
        key = f"{str(Path(image.path).stem)}"

        submission_strings[key] = IMAGE_SUBMISSION_STRING_TEMPLATE.format(
            config_file=config_file,
            image_path=image.path,
            bids_dir=bids_dir,
            fmriprep_dir=fmriprep_dir,
            pybids_db_path=pybids_db_path,
            out_dir=out_dir,
            subject_out_dir=subject_out_dir,
            processing_stream=processing_stream,
            subject_working_dir=subject_working_dir,
            log_dir=log_dir,
            debug=debug_flag,
        )
        logger.debug(submission_strings[key])
    return submission_strings


def _populate_batch_manager(batch_manager, submission_strings, logger):
    logger.info("Setting up batch manager with jobs to run.")

    for key in submission_strings.keys():
        batch_manager.addjob(Job(key, submission_strings[key]))

    batch_manager.createsubmissionhead()
    batch_manager.compilejobstrings()


def _setup_batch_manager(config: ProjectOptions, non_processing=False):
    batch_manager= BatchManager(config.batch_config_path, config.postprocessing.batch_log_dir)
    batch_manager.update_mem_usage(config.postprocessing.batch_options.memory_usage)
    batch_manager.update_time(config.postprocessing.batch_options.time_usage)
    batch_manager.update_nthreads(config.postprocessing.batch_options.n_threads)
    batch_manager.update_email(config.email_address)

    if non_processing:
        batch_manager.update_mem_usage(2000)
        batch_manager.update_nthreads(1)
        batch_manager.update_time("0:30:0")

    return batch_manager


def _get_subject_working_dir(working_dir, out_dir, subject_id, processing_stream):
    # If no top-level working directory is provided, make one in the out_dir
    if not working_dir:
        subject_working_dir = (
            out_dir / "working" / processing_stream / ("sub-" + subject_id)
        )
    # Otherwise, use the provided top-level directory as a base,
    #   and name working directory after the subject
    else:
        subject_working_dir = (
            Path(working_dir) / processing_stream / ("sub-" + subject_id)
        )

    return subject_working_dir
