import pytest

from clpipe.postprocutils.image_workflows import *
from clpipe.postprocutils.confounds_workflows import build_confounds_processing_workflow


def test_spatial_smoothing_wf(
    artifact_dir, request, sample_raw_image, sample_raw_image_mask, helpers
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    out_path = test_path / "smoothed.nii.gz"
    wf = build_SUSAN_workflow(
        in_file=sample_raw_image,
        out_file=out_path,
        fwhm_mm=6,
        mask_path=sample_raw_image_mask,
        base_dir=test_path,
        crashdump_dir=test_path,
    )

    wf.write_graph(dotfilename=test_path / "filteredflow", graph2use="colored")

    wf.run()

    helpers.plot_4D_img_slice(out_path, "smoothed.png")
    helpers.plot_timeseries(out_path, sample_raw_image)


def test_spatial_smoothing_wf_no_mask(artifact_dir, request, sample_raw_image, helpers):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    out_path = test_path / "smoothed.nii.gz"
    wf = build_SUSAN_workflow(
        in_file=sample_raw_image,
        out_file=out_path,
        fwhm_mm=6,
        base_dir=test_path,
        crashdump_dir=test_path,
    )

    wf.write_graph(dotfilename=test_path / "filteredflow", graph2use="colored")

    wf.run()

    helpers.plot_4D_img_slice(out_path, "smoothed.png")
    helpers.plot_timeseries(out_path, sample_raw_image)


def test_calculate_100_voxel_mean_wf(
    artifact_dir, sample_raw_image, plot_img, write_graph, request, helpers
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    out_path = test_path / "normalized_100vm.nii.gz"
    wf = build_100_voxel_mean_workflow(
        in_file=sample_raw_image,
        out_file=out_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    if write_graph:
        wf.write_graph(
            dotfilename=test_path / "calc100voxelMeanFlow", graph2use=write_graph
        )

    if plot_img:
        helpers.plot_4D_img_slice(out_path, "normalized_100vm.png")

    assert True


def test_calculate_10000_global_median_wf(
    artifact_dir,
    sample_raw_image,
    sample_raw_image_mask,
    plot_img,
    write_graph,
    request,
    helpers,
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    out_path = test_path / "normalized_10000gm.nii.gz"

    wf = build_10000_global_median_workflow(
        in_file=sample_raw_image,
        out_file=out_path,
        mask_file=sample_raw_image_mask,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    helpers.plot_timeseries(out_path, sample_raw_image)

    if write_graph:
        wf.write_graph(
            dotfilename=test_path / "calc10000globalMedianFlow", graph2use=write_graph
        )

    if plot_img:
        helpers.plot_4D_img_slice(out_path, "normalized_10000gm.png")

    assert True


def test_butterworth_filter_wf(
    artifact_dir, sample_raw_image, plot_img, write_graph, request, helpers
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    filtered_path = test_path / "sample_raw_filtered.nii"

    wf = build_butterworth_filter_workflow(
        hp=0.008,
        lp=-1,
        tr=2,
        order=2,
        in_file=sample_raw_image,
        out_file=filtered_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    if write_graph:
        wf.write_graph(dotfilename=test_path / "filteredflow", graph2use=write_graph)

    if plot_img:
        helpers.plot_4D_img_slice(filtered_path, "filtered.png")

    assert True


def test_fslmath_temporal_filter_wf(
    artifact_dir, sample_raw_image, plot_img, write_graph, request, helpers
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    filtered_path = test_path / "sample_raw_filtered.nii.gz"

    wf = build_fslmath_temporal_filter(
        hp=0.008,
        lp=-1,
        tr=2,
        in_file=sample_raw_image,
        out_file=filtered_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.write_graph(dotfilename=test_path / "filteredflow", graph2use="colored")

    wf.run()

    helpers.plot_timeseries(filtered_path, sample_raw_image)

    

    if plot_img:
        helpers.plot_4D_img_slice(filtered_path, "filtered.png")

    assert True

class TestWorkflows:
    highlight_ranges = None

    def teardown(self):
        """All workflow tests share these steps once their workflow is setup."""
        self.wf.write_graph(dotfilename = self.test_path / "wf_diagram", graph2use="orig")
        self.wf.run()
        

        self.helpers.plot_timeseries(
            self.export_path, self.sample_raw_image, 
            highlight_ranges=self.highlight_ranges,
            num_figs=1
            )

        if self.plot_img:
            self.helpers.plot_4D_img_slice(self.export_path, "sample_processed.png")

    def test_3dtproject_temporal_filter_wf(self):
        """Test the basic case of running the workflow."""
        
        self.wf = build_3dtproject_temporal_filter(
            bpHigh= .9, bpLow= 0.005, tr=2,
            import_file=self.sample_raw_image,
            export_file=self.export_path,
            base_dir=self.test_path, crashdump_dir=self.test_path,
            mask_file=self.sample_raw_image_mask
        )
        
    def test_3dtproject_temporal_filter_wf_scrubs(self):
        """Test the basic case of running the workflow."""

        self.wf = build_3dtproject_temporal_filter(
            bpHigh= .9, bpLow= 0.005, tr=2,
            scrub_targets=True,
            import_file=self.sample_raw_image,
            export_file=self.export_path,
            base_dir=self.test_path, crashdump_dir=self.test_path,
            mask_file=self.sample_raw_image_mask
        )
        scrub_targets = [1] * 100
        scrub_targets[46:52] = [0] * 6
        self.highlight_ranges = [(45.5, 52.5)]
        self.wf.inputs.inputnode.scrub_targets = scrub_targets

    @pytest.fixture(autouse=True)
    def _test_path(self, request, artifact_dir):
        """Setup an artifact directory for the currently running test."""
        self.test_path = artifact_dir / request.module.__name__ / request.node.name
        self.test_path.mkdir(parents=True, exist_ok=True)
        self.export_path = self.test_path / "sample_processed.nii.gz"

    @pytest.fixture(autouse=True)
    def _request_fixtures(self, sample_raw_image_longer, sample_raw_image_mask, helpers, plot_img):
        """Import fixtures from conftest to be used by the class. Done here instead
            of in a 'setup' function because fixtures can only be requested by tests
            or other fixtures."""
        self.sample_raw_image = sample_raw_image_longer
        self.sample_raw_image_mask = sample_raw_image_mask
        self.helpers = helpers
        self.plot_img = plot_img


@pytest.mark.skip(reason="Needs to be fixed but not prioritized")    
def test_confound_regression_fsl_glm_wf(artifact_dir, sample_raw_image, sample_postprocessed_confounds, sample_raw_image_mask, plot_img, write_graph, request, helpers):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    regressed_path = test_path / "sample_raw_regressed.nii"

    wf = build_confound_regression_fsl_glm_workflow(
        confound_file=sample_postprocessed_confounds,
        in_file=sample_raw_image,
        out_file=regressed_path,
        mask_file=sample_raw_image_mask,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    if write_graph:
        wf.write_graph(dotfilename=test_path / "regressedFlow", graph2use=write_graph)

    if plot_img:
        helpers.plot_4D_img_slice(regressed_path, "regressed.png")


def test_confound_regression_afni_3dTproject_wf(
    artifact_dir,
    sample_raw_image,
    sample_postprocessed_confounds,
    sample_raw_image_mask,
    plot_img,
    write_graph,
    request,
    helpers,
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    regressed_path = test_path / "sample_raw_regressed.nii.gz"

    wf = build_confound_regression_afni_3dTproject(
        confounds_file=sample_postprocessed_confounds,
        in_file=sample_raw_image,
        out_file=regressed_path,
        mask_file=sample_raw_image_mask,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    helpers.plot_timeseries(regressed_path, sample_raw_image)

    if write_graph:
        wf.write_graph(dotfilename=test_path / "regressedFlow", graph2use=write_graph)

    if plot_img:
        helpers.plot_4D_img_slice(regressed_path, "regressed.png")


def test_apply_aroma_fsl_regfilt_wf(
    artifact_dir,
    sample_raw_image,
    sample_melodic_mixing,
    sample_aroma_noise_ics,
    sample_raw_image_mask,
    plot_img,
    write_graph,
    request,
    helpers,
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    regressed_path = test_path / "sample_raw_aroma.nii.gz"

    wf = build_aroma_workflow_fsl_regfilt(
        mixing_file=sample_melodic_mixing,
        noise_file=sample_aroma_noise_ics,
        in_file=sample_raw_image,
        out_file=regressed_path,
        mask_file=sample_raw_image_mask,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    helpers.plot_timeseries(regressed_path, sample_raw_image)

    if write_graph:
        wf.write_graph(dotfilename=test_path / "aromaflow", graph2use=write_graph)

    if plot_img:
        helpers.plot_4D_img_slice(regressed_path, "aromaaplied.png")

@pytest.mark.skip(reason="Need to provide reference image")
def test_resample_wf(
    artifact_dir,
    sample_raw_image,
    sample_reference,
    plot_img,
    write_graph,
    request,
    helpers,
):
    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    resampled_path = test_path / "resampled.nii.gz"

    wf = build_resample_workflow(
        reference_image=sample_reference,
        in_file=sample_raw_image,
        out_file=resampled_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

    if write_graph:
        wf.write_graph(dotfilename=test_path / "resampleflow", graph2use=write_graph)

    if plot_img:
        helpers.plot_4D_img_slice(resampled_path, "resample.png")


## Just make a function that makes a map node (instantiates it and tests the construction of the map node.


def test_build_multiple_scrubbing_workflow(
    sample_confounds_timeseries,
    postprocessing_config,
    helpers,
    artifact_dir,
    request,
):
    import os
    from nipype import Node, Workflow
    from nipype.interfaces.utility import IdentityInterface

    test_path = helpers.create_test_dir(artifact_dir, request.node.name)

    postprocessing_config["ProcessingStepOptions"]["ScrubTimepoints"][1][
        "Threshold"
    ] = 0.13

    # Create an input node for the workflow
    input_node = Node(
        IdentityInterface(fields=["confounds_file", "scrub_configs"]), name="inputnode"
    )
    input_node.inputs.confounds_file = (
        sample_confounds_timeseries  # path to the sample confounds timeseries
    )

    # Fetch the list of scrub configs from the default postprocessing config
    scrub_configs = postprocessing_config["ProcessingStepOptions"]["ScrubTimepoints"]

    # Feed the scrub config list of dicts into the mapper via the workflow inputnode
    input_node.inputs.scrub_configs = scrub_configs

    # Define the output node for the workflow
    output_node = Node(IdentityInterface(fields=["scrub_vector"]), name="outputnode")

    # Define the function node
    scrub_target_node = pe.MapNode(
        Function(
            input_names=["confounds_file", "scrub_configs"],
            output_names=["scrub_vector"],
            function=get_scrub_vector_node,
        ),
        iterfield=["scrub_configs"],
        name="get_scrub_vector_map_node",
    )

    # Set the input parameters of the node
    scrub_target_node.inputs.scrub_configs = scrub_configs

    # Create a new workflow to hold only the scrub_target_node
    test_wf = Workflow(name="test_wf")
    test_wf.add_nodes([input_node, scrub_target_node, output_node])
    test_wf.connect(input_node, "confounds_file", scrub_target_node, "confounds_file")
    test_wf.connect(input_node, "scrub_configs", scrub_target_node, "scrub_configs")
    test_wf.connect(scrub_target_node, "scrub_vector", output_node, "scrub_vector")

    # Run the workflow
    test_wf.base_dir = os.path.join(
        test_path, "work_dir"
    )  # specify the working directory for the workflow
    test_wf.run()

    # Write the workflow graph if needed
    test_wf.write_graph(
        graph2use="colored",
        dotfilename=os.path.join(test_path, "test_wf_graph.dot"),
    )

    # Further validation can be added here, like checking the output files or their properties

    # Further validation can be added here, like checking the output files or their properties


def test_scrubbing_wf(artifact_dir, sample_raw_image, plot_img, request, helpers):
    """Test that a list of arbitrary timepoints can be scrubbed from an image."""

    test_path = helpers.create_test_dir(artifact_dir, request.node.name)
    scrubbed_path = test_path / "scrubbed.nii.gz"

    scrub_vector = [0, 1, 0, 0, 0, 0, 1, 0, 0, 0]

    wf = build_scrubbing_workflow(
        scrub_vector,
        import_path=sample_raw_image,
        export_path=scrubbed_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )

    wf.write_graph(dotfilename=test_path / "scrubbed_flow", graph2use="colored")

    wf.run()

    helpers.plot_timeseries(scrubbed_path, sample_raw_image)

    if plot_img:
        helpers.plot_4D_img_slice(scrubbed_path, "scrubbed.png")


def test_scrubbing_wf_no_insert_na(
    artifact_dir, sample_raw_image, plot_img, request, helpers
):
    """Test that a list of arbitrary timepoints can be scrubbed from an image."""

    test_path = helpers.create_test_dir(artifact_dir, request.node.name)
    scrubbed_path = test_path / "scrubbed.nii.gz"

    scrub_vector = [0, 1, 0, 0, 0, 0, 1, 0, 0, 0]

    wf = build_scrubbing_workflow(
        scrub_vector,
        import_path=sample_raw_image,
        insert_na=False,
        export_path=scrubbed_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )

    wf.write_graph(dotfilename=test_path / "scrubbed_flow", graph2use="colored")

    wf.run()

    helpers.plot_timeseries(scrubbed_path, sample_raw_image)

    if plot_img:
        helpers.plot_4D_img_slice(scrubbed_path, "scrubbed.png")


@pytest.mark.skip(reason="Need to wrap tsv as image.")
def test_scrubbing_wf_confounds(
    artifact_dir, sample_confounds_timeseries, request, helpers
):
    """Test that a list of arbitrary timepoints can be scrubbed from a confounds file."""

    test_path = helpers.create_test_dir(artifact_dir, request.node.name)
    scrubbed_path = test_path / "scrubbed_confounds.tsv"

    scrub_vector = [0, 1, 0, 0, 0, 0, 1, 0, 0, 0]

    wf = build_scrubbing_workflow(
        scrub_vector,
        import_path=sample_confounds_timeseries,
        export_path=scrubbed_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()

@pytest.mark.skip(reason="Need to wrap tsv as image.")
def test_scrubbing_wf_aroma(artifact_dir, sample_melodic_mixing, request, helpers):
    """Test that a list of arbitrary timepoints can be scrubbed from an
    AROMA mixing file."""

    test_path = helpers.create_test_dir(artifact_dir, request.node.name)
    scrubbed_path = test_path / "scrubbed_melodic_mixing.tsv"

    scrub_vector = [0, 1, 0, 0, 0, 0, 1, 0, 0, 0]

    wf = build_scrubbing_workflow(
        scrub_vector,
        import_path=sample_melodic_mixing,
        export_path=scrubbed_path,
        base_dir=test_path,
        crashdump_dir=test_path,
    )
    wf.run()
