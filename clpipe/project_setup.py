import os
import click
from .config_json_parser import ClpipeConfigParser
from pkg_resources import resource_stream
import json

from .utils import get_logger, add_file_handler
from .config import DEFAULT_CONFIG_PATH, DEFAULT_CONFIG_FILE_NAME, \
    CLICK_DIR_TYPE_NOT_EXIST, CLICK_DIR_TYPE_EXISTS, LOG_DIR_HELP

COMMAND_NAME = "setup"
DEFAULT_DICOM_DIR = 'data_DICOMs'
DCM2BIDS_SCAFFOLD_TEMPLATE = 'dcm2bids_scaffold -o {}'

PROJECT_DIR_HELP = "Where the project will be located."
SOURCE_DATA_HELP = \
    "Where the raw data (usually DICOMs) are located."
MOVE_SOURCE_DATA_HELP = \
    "Move source data into project/data_DICOMs folder. USE WITH CAUTION."
SYM_LINK_HELP = \
    "Symlink the source data into project/data_dicoms. Usually safe to do."


@click.command(COMMAND_NAME)
@click.option('-project_title', required=True, default=None)
@click.option('-project_dir', required=True ,type=CLICK_DIR_TYPE_NOT_EXIST,
              default=None, help=PROJECT_DIR_HELP)
@click.option('-source_data', type=CLICK_DIR_TYPE_EXISTS,
              help=SOURCE_DATA_HELP)
@click.option('-move_source_data', is_flag=True, default=False,
              help=MOVE_SOURCE_DATA_HELP)
@click.option('-symlink_source_data', is_flag=True, default=False,
              help=SYM_LINK_HELP)
@click.option('-log_dir', type=CLICK_DIR_TYPE_EXISTS, help=LOG_DIR_HELP)

def project_setup_cli(project_title=None, project_dir=None, source_data=None, 
                      move_source_data=None, symlink_source_data=None, log_dir=None):
    """Set up a clpipe project"""

    project_setup(
        project_title=project_title, 
        project_dir=project_dir, source_data=source_data, 
        move_source_data=move_source_data,
        symlink_source_data=symlink_source_data,
        log_dir=log_dir)


def project_setup(project_title=None, project_dir=None, 
                  source_data=None, move_source_data=None,
                  symlink_source_data=None, log_dir=None):

    config_parser = ClpipeConfigParser()
    config = config_parser.config
    org_source = os.path.abspath(source_data)

    bids_dir = config.config['DICOMToBIDSOptions']['BIDSDirectory']
    project_dir = config.config['ProjectDirectory']
    conv_config = config.config['DICOMToBIDSOptions']['ConversionConfig']
    #WHAT IS THE FIRST ARGUMENT DOING? - Not too sure. Seems to be setting up the directories in config file, but it doesnt make sense to run the next line in this file?
    log_dir = config.config['DICOMToBIDSOptions']['LogDirectory']

    add_file_handler(os.path.join(project_dir, "logs"))
    logger = get_logger(STEP_NAME, debug=debug)

    # Create the project directory
    os.makedirs(project_dir, exist_ok=True)
    logger.debug(f"Created project directory at: {project_dir}")

    if move_source_data or symlink_source_data:
        source_data = os.path.join(os.path.abspath(project_dir), 
            DEFAULT_DICOM_DIR)
        logger.debug(f"Created path for source directory at: {source_data}")
    
    logger.info(f"Starting Project Setup with Title as: {project_title}")
    config_parser.setup_project(project_title, project_dir, source_data)
    logger.info('Completed Project Setup')
    
    if symlink_source_data:
        logger.info('Starting SymLink for source data to project/data_DICOMs')
        os.symlink(
            os.path.abspath(org_source),
            os.path.join(os.path.abspath(project_dir), DEFAULT_DICOM_DIR)
        )
    
    # Create an empty BIDS directory
    os.system(DCM2BIDS_SCAFFOLD_TEMPLATE.format(bids_dir))
    logger.debug(f"Created empty BIDS directory at: {bids_dir}")

    logger.info('Creating JSON Config File')
    config.config_json_dump(project_dir, DEFAULT_CONFIG_FILE_NAME)

    with resource_stream(__name__, DEFAULT_CONFIG_PATH) as def_conv_config:
        conv_config = json.load(def_conv_config)
        logger.debug('JSON object loaded')

    with open(conv_config, 'w') as fp:
        json.dump(conv_config, fp, indent='\t')
        logger.debug('JSON indentation completed')######################

    os.makedirs(os.path.join(project_dir, 'analyses'), 
                exist_ok=True)
    logger.debug('Created empty analyses directory')

    os.makedirs(os.path.join(project_dir, 'scripts'), 
                exist_ok=True)
    logger.debug('Created empty scripts directory')