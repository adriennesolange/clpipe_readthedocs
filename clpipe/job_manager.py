import json
from pkg_resources import resource_stream
import os

from .utils import get_logger
from clpipe.config.options import BatchManagerConfig

# TODO: We need to update the batch manager to be more flexible,
# so as to allow for no-quotes, no equals, and to not have various options
# for example, BIAC doesn't have time or number of cores as options.

LOGGER_NAME = "job-manager"
OUTPUT_FORMAT_STR = "Output-{jobid}-jobid-%j.out"
JOB_ID_FORMAT_STR = "{jobid}"
MAX_JOB_DISPLAY = 5
DEFAULT_BATCH_CONFIG_PATH = "slurmUNCConfig.json"

SLURMUNCCONFIG: str = "clpipe/batchConfigs/slurmUNCConfig.json"


class JobManager:
    def __init__(self, output_directory=None, debug=False):
        self.debug = debug
        self.logger = get_logger(LOGGER_NAME, debug=debug)
        if output_directory is None:
            self.logger.warning(
                ("No output directory provided " "- defaulting to current directory")
            )
            output_directory = "."

        self.logger.info(f"Batch job output path: {output_directory}")  # Adjust this
        self.output_dir = os.path.abspath(output_directory)
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)
            self.logger.debug(f"Created batch output directory at: {output_directory}")

        self.job_queue = []

        def print_jobs(self):
            job_count = len(self.job_queue)

            if job_count == 0:
                output = "No jobs to run."
            else:
                output = "Jobs to run:\n\n"
                for index, job in enumerate(self.job_queue):
                    output += "\t" + job + "\n\n"
                    if (
                        index == MAX_JOB_DISPLAY - 1
                        and job_count > MAX_JOB_DISPLAY
                        and not self.debug
                    ):
                        output += f"\t...and {job_count - 5} more job(s).\n"
                        break
                output += "Re-run with the '-submit' flag to launch these jobs."
            self.logger.info(output)

        def add_jobs(self):
            ...

        def submit_jobs(self):
            ...


class BatchJobManager(JobManager):
    def __init__(
        self,
        batch_system_config: os.PathLike,
        output_directory=None,
        debug=False,
        mem_use=None,
        time=None,
        threads=None,
        email=None,
    ):
        super.__init__(output_directory, debug)
        self.config = BatchManagerConfig.load(batch_system_config)

        self.config.mem_use = mem_use
        self.config.time = time
        self.config.threads = threads
        self.config.email = email

        self.header = self.create_submission_head()

    def create_submission_head(self):
        head = [self.config.submission_head]
        for e in self.config.submission_options:
            temp = e["command"] + " " + e["args"]
            head.append(temp)
        for e in self.config.sub_options_equal:
            temp = e["command"] + "=" + e["args"]
            head.append(temp)

        head.append(self.config.memory_command.format(mem=self.config.memory_default))
        if self.config.time_command_active:
            head.append(self.config.TimeCommand.format(time=self.config.time_default))
        if self.config.thread_command_active:
            head.append(
                self.config.n_threads_command.format(nthreads=self.config.n_threads)
            )
        if self.config.job_id_command_active:
            head.append(self.config.job_id_command.format(jobid=JOB_ID_FORMAT_STR))
        if self.config.output_command_active:
            head.append(
                self.config.output_command.format(
                    output=os.path.abspath(
                        os.path.join(self.output_dir, OUTPUT_FORMAT_STR)
                    )
                )
            )
        if self.config.email_address:
            head.append(
                self.config.email_address.format(email=self.config.email_address)
            )
        head.append(self.config.command_wrapper)

        return " ".join(head)

    def add_job(self, job_id, job_string):
        job = Job(job_id, job_string)
        job_string = self.header.format(job_id=job.job_id, cmdwrap=job.job_string)
        self.job_queue.append(Job(job_id, job_string))

    def submit_jobs(self):
        self.logger.info(f"Submitting {len(self.job_queue)} job(s) in batch.")
        self.logger.debug(f"Memory usage: {self.config.memory_default}")
        self.logger.debug(f"Time usage: {self.config.time_default}")
        self.logger.debug(f"Number of threads: {self.config.n_threads}")
        self.logger.debug(f"Email: {self.config.email_address}")
        for job in self.job_queue:
            os.system(job.job_string)


class LocalJobManager(JobManager):
    def __init__(self, output_directory=None, debug=False):
        super().__init__(output_directory, debug)

    def add_job(self, job_id, job_string):
        job = Job(job_id, job_string)
        self.job_queue.append(job)

    def submit_jobs(self):
        self.logger.info(f"Submitting {len(self.job_queue)} job(s) locally.")
        for job in self.job_queue:
            os.system(job.string)


class JobManagerFactory:
    def get(
        self,
        batch_config=None,
        output_directory=None,
        mem_use=None,
        time=None,
        threads=None,
        email=None,
    ) -> JobManager:
        """
        Initializes a JobRunner object.

        Args:
            method (str): "batch / Local"
            The method to be used for running the job.
        """
        if batch_config:
            return BatchJobManager(
                batch_config, output_directory, mem_use, time, threads, email
            )
        else:
            return LocalJobManager()


class Job:
    def __init__(self, job_id, job_string):
        self.job_id = job_id
        self.job_string = job_string
