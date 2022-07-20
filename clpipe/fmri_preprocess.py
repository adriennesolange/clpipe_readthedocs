import os
import sys
import logging

from .batch_manager import BatchManager, Job
from .config_json_parser import ClpipeConfigParser
from .error_handler import exception_handler
from .utils import get_logger, add_file_handler

BASE_SINGULARITY_CMD = (
    "unset PYTHONPATH; {templateflow1} singularity run -B {templateflow2}"
    "{bindPaths} {batchcommands} {fmriprepInstance} {bids_dir} {output_dir} "
    "participant --participant-label {participantLabels} -w {working_dir} "
    "--fs-license-file {fslicense} {threads} {useAROMA} {other_opts}"
)

BASE_DOCKER_CMD = (
    "docker run --rm -ti "
    "-v {fslicense}:/opt/freesurfer/license.txt:ro "
    "-v {bids_dir}:/data:ro -v {output_dir}:/out "
    "-v {working_dir}:/work "
    "{docker_fmriprep} /data /out participant -w /work {threads} {useAROMA} "
    "{other_opts} --participant-label {participantLabels}"
)

TEMPLATE_1 = "export SINGULARITYENV_TEMPLATEFLOW_HOME={templateflowpath};"
TEMPLATE_2 = \
    "${{TEMPLATEFLOW_HOME:-$HOME/.cache/templateflow}}:{templateflowpath},"
USE_AROMA_FLAG = "--use-aroma"
N_THREADS_FLAG = "--nthreads"



def fmriprep_process(bids_dir=None, working_dir=None, output_dir=None, 
                     config_file=None, subjects=None, log_dir=None,
                     submit=False, debug=False):
    """
    This command runs a BIDS formatted dataset through fMRIprep. 
    Specify subject IDs to run specific subjects. If left blank,
    runs all subjects.
    """

    config = ClpipeConfigParser()
    config.config_updater(config_file)
    config.setup_fmriprep_directories(
        bids_dir, working_dir, output_dir, log_dir
    )

    config = config.config
    project_dir = config.config["ProjectDirectory"]
    bids_dir = config['FMRIPrepOptions']['BIDSDirectory']
    working_dir = config['FMRIPrepOptions']['WorkingDirectory']
    output_dir = config['FMRIPrepOptions']['OutputDirectory']
    log_dir = config['FMRIPrepOptions']['LogDirectory']
    template_flow_path = config["FMRIPrepOptions"]["TemplateFlowPath"]
    batch_config = config['BatchConfig']
    mem_usage = config['FMRIPrepOptions']['FMRIPrepMemoryUsage']
    time_usage = config['FMRIPrepOptions']['FMRIPrepTimeUsage']
    n_threads = config['FMRIPrepOptions']['NThreads']
    email = config["EmailAddress"]
    thread_command_active = batch_manager.config['ThreadCommandActive']
    cmd_line_opts = config['FMRIPrepOptions']['CommandLineOpts']
    use_aroma = config['FMRIPrepOptions']['UseAROMA']
    docker_toggle = config['FMRIPrepOptions']['DockerToggle']
    docker_fmriprep_version = \
        config['FMRIPrepOptions']['DockerFMRIPrepVersion']
    freesurfer_license_path = \
        config['FMRIPrepOptions']['FreesurferLicensePath']
    batch_commands = batch_manager.config["FMRIPrepBatchCommands"]
    singularity_bind_paths = batch_manager.config['SingularityBindPaths']
    fmriprep_path = config['FMRIPrepOptions']['FMRIPrepPath']

    add_file_handler(os.path.join(project_dir, "logs"))
    logger = get_logger("fmriprep_process", debug=debug)

    if not any([bids_dir, output_dir, working_dir, log_dir]):
        logger.error(
            'Please make sure the BIDS, working and output directories are '
            'specified in either the configfile or in the command. '
            'At least one is not specified.'
        )
        sys.exit(1)

    logger.info(f"Starting fMRIprep job targeting: {bids_dir}")

    template_1 = ""
    template_2 = ""
    if config['FMRIPrepOptions']['TemplateFlowToggle']:
        logger.debug("Template Flow toggle: ON")
        logger.debug(f"Template Flow path: {template_flow_path}")
        template_1 = TEMPLATE_1.format(
            templateflowpath = template_flow_path
        )
        template_2 = TEMPLATE_2.format(
            templateflowpath = template_flow_path
        )
        
    other_opts = cmd_line_opts
    use_aroma = ""
    if USE_AROMA_FLAG in other_opts:
        logger.debug("Use AROMA: ON")
    elif use_aroma:
        logger.debug("Use AROMA: ON")
        use_aroma = USE_AROMA_FLAG

    if not subjects:
        sublist = [o.replace('sub-', '') for o in os.listdir(bids_dir)
                   if os.path.isdir(os.path.join(bids_dir, o)) and 'sub-' in o]
    else:
        sublist = subjects
    logger.info(f"Targeting subject(s): {', '.join(sublist)}")

    batch_manager = BatchManager(batch_config, log_dir)
    batch_manager.update_mem_usage(mem_usage)
    batch_manager.update_time(time_usage)
    batch_manager.update_nthreads(n_threads)
    batch_manager.update_email(email)

    threads = ''
    if thread_command_active:
        logger.debug("Threads command: ACTIVE")
        threads = f'{N_THREADS_FLAG} ' + batch_manager.get_threads_command()[1]
        
    fmriprep_args = {
        "bids_dir": bids_dir,
        "output_dir": output_dir,
        "working_dir": working_dir,
        "participant_label": sub,
        "fslicense": freesurfer_license_path,
        "threads": threads,
        "useAROMA": use_aroma,
        "other_opts": other_opts
    }

    for sub in sublist:
        if docker_toggle:
            logger.debug("Using container type: Docker")
            fmriprep_args["docker_fmriprep"] = docker_fmriprep_version    
        else:
            logger.debug("Using container type: Singularity")
            fmriprep_args["templateflow1"] = template_1
            fmriprep_args["templateflow2"] = template_2
            fmriprep_args["fmriprepInstance"] = fmriprep_path
            fmriprep_args["batchcommands"] = batch_commands
            fmriprep_args["bindPaths"] = singularity_bind_paths

        submission_string = BASE_DOCKER_CMD.format(**fmriprep_args)
        batch_manager.addjob(
            Job("sub-" + sub + "_fmriprep", submission_string)
        )

    batch_manager.compilejobstrings()
    if submit:
        batch_manager.submit_jobs()
    else:
        batch_manager.print_jobs()
