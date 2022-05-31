import os

from math import sqrt, log
import copy
import pkg_resources

#TODO: import these without specifying, to help with code readability
from nipype.interfaces.fsl.maths import MeanImage, BinaryMaths, MedianImage, ApplyMask, TemporalFilter
from nipype.interfaces.fsl.utils import ImageStats, FilterRegressor
from nipype.interfaces.afni import TProject
from nipype.interfaces.fsl.model import GLM
from nipype.interfaces.fsl import SUSAN, FLIRT
from nipype.interfaces.utility import Function, Merge, IdentityInterface
from nipype.interfaces.io import ExportFile
import nipype.pipeline.engine as pe

from .nodes import build_input_node, build_output_node, ButterworthFilter, RegressAromaR, ImageSlice
import clpipe.postprocutils.r_setup

RESCALING_10000_GLOBALMEDIAN = "globalmedian_10000"
RESCALING_100_VOXELMEAN = "voxelmean_100"
NORMALIZATION_METHODS = (RESCALING_10000_GLOBALMEDIAN, RESCALING_100_VOXELMEAN)


class AlgorithmNotFoundError(ValueError):
    pass


def build_postprocessing_workflow(postprocessing_config: dict, in_file: os.PathLike=None, export_file:os.PathLike=None,
    name:str = "Postprocessing_Pipeline", processing_steps: list=None, mask_file: os.PathLike=None, mixing_file: os.PathLike=None, 
    noise_file: os.PathLike=None, confound_file: os.PathLike = None, tr: float = None,
    base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    
    postproc_wf = pe.Workflow(name=name, base_dir=base_dir)
    
    if crashdump_dir is not None:
        postproc_wf.config['execution']['crashdump_dir'] = crashdump_dir
    
    if processing_steps is None:
        processing_steps = postprocessing_config["ProcessingSteps"]
    step_count = len(processing_steps)

    if step_count < 1:
        raise ValueError("The PostProcess workflow requires at least 1 processing step.")

    input_node = pe.Node(IdentityInterface(fields=['in_file', 'export_file'], mandatory_inputs=False), name="inputnode")
    output_node = pe.Node(IdentityInterface(fields=['out_file'], mandatory_inputs=True), name="outputnode")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file

    current_wf = None
    prev_wf = None

    # Iterate through list of processing steps, adding a new sub workflow for each step
    for index, step in enumerate(processing_steps):
        # Decide which wf to add next
        if step == "TemporalFiltering":
            if not tr:
                raise ValueError(f"Missing TR corresponding to image: {in_file}")
            hp = postprocessing_config["ProcessingStepOptions"][step]["FilteringHighPass"]
            lp = postprocessing_config["ProcessingStepOptions"][step]["FilteringLowPass"]
            order = postprocessing_config["ProcessingStepOptions"][step]["FilteringOrder"]
            algorithm_name = postprocessing_config["ProcessingStepOptions"][step]["Algorithm"]

            temporal_filter_algorithm = _getTemporalFilterAlgorithm(algorithm_name)

            current_wf = temporal_filter_algorithm(hp=hp,lp=lp, tr=tr, order=order, base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)
        
        elif step == "IntensityNormalization":
            algorithm_name = postprocessing_config["ProcessingStepOptions"][step]["Algorithm"]

            intensity_normalization_algorithm = _getIntensityNormalizationAlgorithm(algorithm_name)

            current_wf = intensity_normalization_algorithm(base_dir=postproc_wf.base_dir, mask_file=mask_file, crashdump_dir=crashdump_dir)
        
        elif step == "SpatialSmoothing":
            fwhm_mm= postprocessing_config["ProcessingStepOptions"][step]["FWHM"]
            #brightness_threshold = postprocessing_config["ProcessingStepOptions"][step]["BrightnessThreshold"]
            algorithm_name = postprocessing_config["ProcessingStepOptions"][step]["Algorithm"]

            spatial_smoothing_algorithm = _getSpatialSmoothingAlgorithm(algorithm_name)

            current_wf = spatial_smoothing_algorithm(base_dir=postproc_wf.base_dir, mask_path=mask_file, fwhm_mm=fwhm_mm, crashdump_dir=crashdump_dir)

        elif step == "AROMARegression":
            algorithm_name = postprocessing_config["ProcessingStepOptions"][step]["Algorithm"]

            apply_aroma_agorithm = _getAROMARegressionAlgorithm(algorithm_name)

            current_wf = apply_aroma_agorithm(mixing_file=mixing_file, noise_file=noise_file, mask_file=mask_file, base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)

        elif step == "ConfoundRegression":
            algorithm_name = postprocessing_config["ProcessingStepOptions"][step]["Algorithm"]

            confound_regression_algorithm = _getConfoundRegressionAlgorithm(algorithm_name)

            column_names = postprocessing_config["ProcessingStepOptions"]["ConfoundRegression"]["Columns"]

            try:
                current_wf = confound_regression_algorithm(mask_file=mask_file, base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)

                # TODO: Need to rework this step to operate off independent confounds_postproc_wf, instead of an internal one here
                # Build a confounds postprocessing workflow to prep confounds for regression
                # confounds_postproc_wf = build_confound_postprocessing_workflow(postprocessing_config,
                #     processing_steps=processing_steps, column_names=column_names,
                #     confound_file=confound_file, mixing_file=mixing_file, noise_file=noise_file, tr=tr,
                #     base_dir=base_dir, crashdump_dir=crashdump_dir)

                # postproc_wf.connect(confounds_postproc_wf, "outputnode.out_file", current_wf, "inputnode.ort")
            
            # This is the case that no operations need to be performed on the confounds file
            except ValueError:
                current_wf = confound_regression_algorithm(mask_file=mask_file, confound_file=confound_file, base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)

        elif step == "TrimTimepoints":
            trim_from_beginning = postprocessing_config["ProcessingStepOptions"][step]["FromEnd"]
            trim_from_end = postprocessing_config["ProcessingStepOptions"][step]["FromBeginning"]

            current_wf = build_trim_timepoints_workflow(trim_from_beginning=trim_from_beginning, trim_from_end=trim_from_end, 
                base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)
        
        elif step == "Resample":
            reference_image = postprocessing_config["ProcessingStepOptions"][step]["ReferenceImage"]
            if reference_image == "SET REFERENCE IMAGE":
                raise ValueError("No reference image provided. Please set a path to reference in clpipe_config.json")

            current_wf = build_resample_workflow(reference_image=reference_image, base_dir=postproc_wf.base_dir, crashdump_dir=crashdump_dir)

        # Send input of postproc workflow to first workflow
        if index == 0:
            postproc_wf.connect(input_node, "in_file", current_wf, "inputnode.in_file")
        # Connect previous wf to current wf
        elif step_count > 1:
            postproc_wf.connect(prev_wf, "outputnode.out_file", current_wf, "inputnode.in_file")
            
        # Keep a reference to current_wf as "prev_wf" for the next loop
        prev_wf = current_wf

    # Connect the output of the last node to postproc workflow's output node
    postproc_wf.connect(prev_wf, "outputnode.out_file", output_node, "out_file")
    if export_file:
        # TODO: Update the postproc workflow to make extension guarentees
        export_node = pe.Node(ExportFile(out_file=export_file, clobber=True, check_extension=False), name="export")
        postproc_wf.connect(current_wf, "outputnode.out_file", export_node, "in_file")

    return postproc_wf


def _getTemporalFilterAlgorithm(algorithmName):
    if algorithmName == "Butterworth":
        return build_butterworth_filter_workflow
    elif algorithmName == "fslmaths":
        return build_fslmath_temporal_filter
    else:
        raise AlgorithmNotFoundError(f"Temporal filtering algorithm not found: {algorithmName}")


def _getIntensityNormalizationAlgorithm(algorithmName):
    if algorithmName == "10000_GlobalMedian":
        return build_10000_global_median_workflow
    else:
        raise AlgorithmNotFoundError(f"Intensity normalization algorithm not found: {algorithmName}")


def _getSpatialSmoothingAlgorithm(algorithmName):
    if algorithmName == "SUSAN":
        return build_SUSAN_workflow
    else:
        raise AlgorithmNotFoundError(f"Spatial smoothing algorithm not found: {algorithmName}")


def _getAROMARegressionAlgorithm(algorithmName):
    if algorithmName == "fsl_regfilt":
        return build_aroma_workflow_fsl_regfilt
    if algorithmName == "fsl_regfilt_R":
        return build_aroma_workflow_fsl_regfilt_R
    else:
        raise AlgorithmNotFoundError(f"AROMA regression algorithm not found: {algorithmName}")


def _getConfoundRegressionAlgorithm(algorithmName):
    if algorithmName == "fsl_glm":
        return build_confound_regression_fsl_glm_workflow
    elif algorithmName == "afni_3dTproject":
        return build_confound_regression_afni_3dTproject
    else:
        raise AlgorithmNotFoundError(f"Confound regression algorithm not found: {algorithmName}")


def build_10000_global_median_workflow(in_file: os.PathLike=None, out_file:os.PathLike=None,
        mask_file: os.PathLike=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    """Perform intensity normalization using the 10,000 global median method.

    Args:
        in_path (os.PathLike): A path to an input .nii to normalize.
        out_path (os.PathLike): A path to save the normalized image.
        mask_path (os.PathLike, optional): A path a mask to apply during the median calculation.
        base_dir (os.PathLike, optional): A path to the base directory for the workflow.
    """

    input_node = build_input_node()
    output_node = build_output_node()
    median_node = pe.Node(ImageStats(op_string="-p 50"), name='global_median')
    mul_10000_node = pe.Node(BinaryMaths(operation="mul", operand_value=10000), name="mul_10000")
    div_median_node = pe.Node(BinaryMaths(operation="div"), name="div_median")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file

    if mask_file:
        median_node.inputs.mask_file = mask_file
        median_node.inputs.op_string = "-k %s -p 50"


    workflow = pe.Workflow(name="10000_Global_Median", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    workflow.connect(input_node, "in_file", median_node, "in_file")
    workflow.connect(input_node, "in_file", mul_10000_node, "in_file")
    workflow.connect(input_node, "out_file", div_median_node, "out_file")

    workflow.connect(mul_10000_node, "out_file", div_median_node, "in_file")
    workflow.connect(median_node, "out_stat", div_median_node, "operand_value")
    workflow.connect(div_median_node, "out_file", output_node, "out_file")
    
    return workflow


def build_100_voxel_mean_workflow(in_file: os.PathLike=None, out_file: os.PathLike=None, base_dir: os.PathLike=None,
    crashdump_dir: os.PathLike=None):
    """Perform intensity normalization using the 100 voxel mean method.

    Args:
        in_path (str): A path to an input .nii to normalize.
        out_path (str): A path to save the normalized image.
    """
    
    if in_file != None:
        mean_image = MeanImage(in_file=in_file)
        mul_math = BinaryMaths(operation='mul', operand_value=100, in_file=in_file)
    else:
        mean_image = MeanImage()
        mul_math = BinaryMaths(operation='mul', operand_value=100)
    
    mean_node = pe.Node(mean_image, name='mean')
    mul100_node = pe.Node(mul_math, name="mul100")

    if out_file != None:
        div_math = BinaryMaths(operation='div', out_file=out_file)
    else:
        div_math = BinaryMaths(operation='div')
    div_mean_node = pe.Node(div_math, name="div_mean") #operand_file=mean_path

    workflow = pe.Workflow(name="100_Voxel_Mean", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    workflow.connect(mul100_node, "out_file", div_mean_node, "in_file")
    workflow.connect(mean_node, "out_file",  div_mean_node, "operand_file")

    return workflow


def build_SUSAN_workflow(in_file: os.PathLike=None, mask_path: os.PathLike=None, fwhm_mm: int=6, out_file: os.PathLike=None, 
    base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    
    workflow = pe.Workflow(name="SUSAN", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir
    
    # Calculate fwhm
    fwhm_to_sigma = sqrt(8 * log(2))
    sigma = fwhm_mm / fwhm_to_sigma
    print(f"fwhm_to_sigma: {fwhm_to_sigma}")

    # Setup identity (pass through) input/output nodes
    input_node = build_input_node()
    output_node = build_output_node()
    
    # Setup nodes to calculate susan threshold inputs
    p2_intensity_node = pe.Node(ImageStats(op_string="-p 2"), name='p2')
    median_intensity_node = pe.Node(ImageStats(op_string="-p 50"), name='median')
    
    # Setup an arbitrary function node to calculate the susan threshold from two scalars with helper function
    susan_thresh_node = pe.Node(Function(inputs_names=["median_intensity", "p2_intensity"], output_names=["susan_threshold"], function=_calc_susan_threshold), name="susan_threshold")

    # Setup susan node
    #   Usage: susan <input> <bt> <dt> <dim> <use_median> <n_usans> [<usan1> <bt1> [<usan2> <bt2>]] <output>
    #   Ref: susan {in_file} {susan_thresh} {sigma} 3 1 1 {temp_tmean} {susan_thresh} {out_file}
    tmean_image_node = pe.Node(MeanImage(), name="mean_image")
    setup_usans_node = pe.Node(Function(input_names=["tmean_image", "susan_threshold"], output_names=["usans_input"], function=_setup_usans_input), name="setup_usans")
    susan_node = pe.Node(SUSAN(fwhm=sigma, use_median=1, dimension=3), name="SUSAN")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
        # mean_image_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file
        
    # Map the input node to the first steps of the susan threshold calculation
    workflow.connect(input_node, "in_file", p2_intensity_node, "in_file")
    workflow.connect(input_node, "in_file", median_intensity_node, "in_file")
    workflow.connect(input_node, "in_file", susan_node, "in_file")
    workflow.connect(input_node, "in_file", tmean_image_node, "in_file")
    workflow.connect(input_node, "out_file", susan_node, "out_file")

    # Setup calculations for susan threshold
    workflow.connect(median_intensity_node, "out_stat", susan_thresh_node, "median_intensity")
    workflow.connect(p2_intensity_node, "out_stat", susan_thresh_node, "p2_intensity")
    workflow.connect(susan_thresh_node, "susan_threshold", susan_node, "brightness_threshold")
    workflow.connect(tmean_image_node, "out_file", setup_usans_node, "tmean_image")
    workflow.connect(susan_thresh_node, "susan_threshold", setup_usans_node, "susan_threshold")
    workflow.connect(setup_usans_node, "usans_input", susan_node, "usans")
    

    # Apply Masking
    if mask_path:
        print(f"Using mask: {mask_path}")
        
        # Setup Masking Node to apply after smoothing
        masker_node = pe.Node(ApplyMask(mask_file=mask_path, output_datatype="float"), name="apply_mask")
        workflow.connect(susan_node, "smoothed_file", masker_node, "in_file")
        workflow.connect(masker_node, "out_file", output_node, "out_file")

        # Add mask to the inputs of the fslstats commands
        p2_intensity_node.inputs.mask_file = mask_path
        median_intensity_node.inputs.mask_file = mask_path
        p2_intensity_node.inputs.op_string = "-k %s -p 2"
        median_intensity_node.inputs.op_string = "-k %s -p 50"
    # Tie the SUSAN output directly to output node if no mask is included
    else:
        workflow.connect(susan_node, "smoothed_file", output_node, "out_file")
        
    return workflow
    

def _calc_susan_threshold(median_intensity, p2_intensity):
    return (median_intensity - p2_intensity) * .75


def _setup_usans_input(tmean_image, susan_threshold):
    return [(tmean_image, susan_threshold)]


def build_butterworth_filter_workflow(hp: float, lp: float, tr: float, order: float=None, in_file: os.PathLike=None, 
    out_file: os.PathLike=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    
    workflow = pe.Workflow(name="Butterworth", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    # Setup identity (pass through) input/output nodes
    input_node = build_input_node()
    output_node = build_output_node()

    butterworth_node = pe.Node(ButterworthFilter(hp=hp,lp=lp,order=order,tr=tr), name="butterworth_filter")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file

    workflow.connect(input_node, "in_file", butterworth_node, "in_file")
    workflow.connect(input_node, "out_file", butterworth_node, "out_file")
    workflow.connect(butterworth_node, "out_file", output_node, "out_file")

    return workflow


def build_fslmath_temporal_filter(hp: float, lp: float, tr: float, order: float=None, in_file: os.PathLike=None, 
    out_file: os.PathLike=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):

    workflow = pe.Workflow(name="fslmaths_Temporal_Filter", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    # Setup identity (pass through) input/output nodes
    input_node = build_input_node()
    output_node = build_output_node()

    fwhm_to_sigma = sqrt(8 * log(2))

    hp_volumes, lp_volumes = -1, -1

    if hp != -1:
        hp_volumes = 1 / (hp * fwhm_to_sigma * tr)
    if lp != -1:
        lp_volumes = 1 / (lp * fwhm_to_sigma * tr)

    mean_image_node = pe.Node(MeanImage(), name="mean_image")
    temporal_filter_node = pe.Node(TemporalFilter(highpass_sigma=hp_volumes, lowpass_sigma=lp_volumes), name="temporal_filter")
    add_node = pe.Node(BinaryMaths(operation='add'), name="add_mean")

     # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file

    workflow.connect(input_node, "in_file", mean_image_node, "in_file")
    workflow.connect(input_node, "in_file", temporal_filter_node, "in_file")
    workflow.connect(mean_image_node, "out_file", add_node, "operand_file")
    workflow.connect(temporal_filter_node, "out_file", add_node, "in_file")
    workflow.connect(add_node, "out_file", output_node, "out_file")

    return workflow


def build_confound_regression_fsl_glm_workflow(in_file: os.PathLike=None, out_file: os.PathLike=None, confound_file: os.PathLike=None, mask_file: os.PathLike=None,
    base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    #TODO: This function currently returns an empy image

    workflow = pe.Workflow(name="Confound_Regression", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    input_node = pe.Node(IdentityInterface(fields=['in_file', 'out_file', 'design_file', 'mask_file'], mandatory_inputs=False), name="inputnode")
    output_node = pe.Node(IdentityInterface(fields=['out_file'], mandatory_inputs=True), name="outputnode")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file
    input_node.inputs.design_file = confound_file

    regressor_node = pe.Node(GLM(), name="fsl_glm")

    workflow.connect(input_node, "in_file", regressor_node, "in_file")
    workflow.connect(input_node, "out_file", regressor_node, "out_res_name")
    workflow.connect(input_node, "design_file", regressor_node, "design")
    workflow.connect(regressor_node, "out_res", output_node, "out_file")

    if mask_file:
        input_node.inputs.mask_file = mask_file
        workflow.connect(input_node, "mask_file", regressor_node, "mask")

    return workflow


def build_confound_regression_afni_3dTproject(in_file: os.PathLike=None, out_file: os.PathLike=None, confound_file: os.PathLike=None, mask_file: os.PathLike=None,
    base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):

    # Referenc command
    # 3dTproject -input {in_file} -prefix {out_file} -ort {to_regress} -polort 0 -mask {brain_mask}

    # Something specific to confound_regression's setup is not letting it work in postproc wf builder

    workflow = pe.Workflow(name="Confound_Regression", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    input_node = pe.Node(IdentityInterface(fields=['in_file', 'out_file', 'ort', 'mask_file'], mandatory_inputs=False), name="inputnode")
    output_node = pe.Node(IdentityInterface(fields=['out_file'], mandatory_inputs=True), name="outputnode")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file
    if confound_file:
        input_node.inputs.ort = confound_file

    regressor_node = pe.Node(TProject(polort=0), name="3dTproject")

    workflow.connect(input_node, "in_file", regressor_node, "in_file")
    workflow.connect(input_node, "out_file", regressor_node, "out_file")
    workflow.connect(input_node, "ort", regressor_node, "ort")
    workflow.connect(regressor_node, "out_file", output_node, "out_file")

    if mask_file:
        input_node.inputs.mask_file = mask_file
        workflow.connect(input_node, "mask_file", regressor_node, "mask")

    return workflow


def build_aroma_workflow_fsl_regfilt(in_file: os.PathLike=None, out_file: os.PathLike=None, mixing_file: os.PathLike=None, noise_file: os.PathLike=None,  
    mask_file: os.PathLike=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):

    workflow = pe.Workflow(name="Apply_AROMA", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    input_node = pe.Node(IdentityInterface(fields=['in_file', 'out_file', 'mixing_file', 'noise_file', 'mask_file'], mandatory_inputs=False), name="inputnode")
    output_node = pe.Node(IdentityInterface(fields=['out_file'], mandatory_inputs=True), name="outputnode")

    regfilt_node = pe.Node(FilterRegressor(), name="regfilt")
    csv_to_list_node = pe.Node(Function(input_names=["csv_file"], output_names=["list"], function=_csv_to_list), name="csv_to_list")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if mixing_file:
        input_node.inputs.mixing_file = mixing_file
    if noise_file:
        input_node.inputs.noise_file = noise_file
    if out_file:
        input_node.inputs.out_file = out_file
    if mask_file:
        input_node.inputs.mask_file = mask_file
        workflow.connect(input_node, "mask_file", regfilt_node, "mask")

    workflow.connect(input_node, "in_file", regfilt_node, "in_file")
    workflow.connect(input_node, "out_file", regfilt_node, "out_file")
    workflow.connect(input_node, "noise_file", csv_to_list_node, "csv_file")
    workflow.connect(csv_to_list_node, "list", regfilt_node, "filter_columns")
    workflow.connect(input_node, "mixing_file", regfilt_node, "design_file")
    workflow.connect(regfilt_node, "out_file", output_node, "out_file")

    return workflow


def build_aroma_workflow_fsl_regfilt_R(in_file: os.PathLike=None, out_file: os.PathLike=None, mixing_file: os.PathLike=None, noise_file: os.PathLike=None,  
    mask_file=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):

    clpipe.postprocutils.r_setup.setup_clpipe_R_lib()
    fsl_regfilt_R_script_path = pkg_resources.resource_filename("clpipe", "data/R_scripts/fsl_regfilt.R")

    workflow = pe.Workflow(name="Apply_AROMA_fsl_regfilt_R", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    input_node = pe.Node(IdentityInterface(fields=['in_file', 'out_file', 'mixing_file', 'noise_file'], mandatory_inputs=False), name="inputnode")
    output_node = pe.Node(IdentityInterface(fields=['out_file'], mandatory_inputs=True), name="outputnode")

    regfilt_R_node = pe.Node(RegressAromaR(script_file=fsl_regfilt_R_script_path, n_threads=4), name="fsl_regfilt_R")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if mixing_file:
        input_node.inputs.mixing_file = mixing_file
    if noise_file:
        input_node.inputs.noise_file = noise_file
    if out_file:
        input_node.inputs.out_file = out_file

    workflow.connect(input_node, "in_file", regfilt_R_node, "in_file")
    #workflow.connect(input_node, "out_file", regfilt_R_node, "out_file")
    workflow.connect(input_node, "mixing_file", regfilt_R_node, "mixing_file")
    workflow.connect(input_node, "noise_file", regfilt_R_node, "noise_file")
    workflow.connect(regfilt_R_node, "out_file", output_node, "out_file")

    return workflow


def build_trim_timepoints_workflow(in_file: os.PathLike=None, 
    out_file: os.PathLike=None, trim_from_beginning=None, trim_from_end=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    workflow = pe.Workflow(name="Trim_Timepoints", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    # Setup identity (pass through) input/output nodes
    input_node = build_input_node()
    output_node = build_output_node()

    slicer_node = pe.Node(ImageSlice(trim_from_beginning=trim_from_beginning, trim_from_end=trim_from_end), name="slicer_node")
    
    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file

    workflow.connect(input_node, "in_file", slicer_node, "in_file")
    workflow.connect(input_node, "out_file", slicer_node, "out_file")
    workflow.connect(slicer_node, "out_file", output_node, "out_file")

    return workflow


def build_resample_workflow(reference_image:os.PathLike=None, in_file: os.PathLike=None, 
    out_file: os.PathLike=None, base_dir: os.PathLike=None, crashdump_dir: os.PathLike=None):
    
    workflow = pe.Workflow(name="Resample", base_dir=base_dir)
    if crashdump_dir is not None:
        workflow.config['execution']['crashdump_dir'] = crashdump_dir

    # Setup identity (pass through) input/output nodes
    input_node = build_input_node()
    output_node = build_output_node()

    resample_node = pe.Node(FLIRT(apply_xfm = True,
                                 reference = reference_image,
                                 uses_qform = True),
                                 name="resample")

    # Set WF inputs and outputs
    if in_file:
        input_node.inputs.in_file = in_file
    if out_file:
        input_node.inputs.out_file = out_file

    workflow.connect(input_node, "in_file", resample_node, "in_file")
    workflow.connect(input_node, "out_file", resample_node, "out_file")
    workflow.connect(resample_node, "out_file", output_node, "out_file")

    return workflow


def _csv_to_list(csv_file):
    # Imports must be in function for running as node
    import numpy as np
    from pathlib import Path

    # Read in the csv
    data = np.loadtxt(csv_file, delimiter=",", dtype=np.int64)
    data_list = list(data)

    return data_list
    