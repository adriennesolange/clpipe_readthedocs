============
Installation
============

    Please note - if you are a UNC-CH user, clpipe is already installed and accessible 
    with the module system. If you are not a UNC-CH user, please start at the section, 
    "Python Environment Setup"

-----------------------
For UNC-CH Users
-----------------------

Getting started on Longleaf
---------------------------

clpipe uses `Longleaf <https://help.rc.unc.edu/longleaf-cluster>`_, a Linux-based HPC
available to researchers across the campus free of charge. All UNC-CH clpipe users will
need a Longleaf account. To request a Longleaf account, follow these `instructions <https://help.rc.unc.edu/request-a-cluster-account/>`_.
Users can access the Longleaf cluster by using either the web-portal, `OnDemand <https://help.rc.unc.edu/ondemand>`_, 
or on the terminal of your local computer. For more instructions on how to use Longleaf see the UNC ITS Research Computing's
Longleaf `guide <https://drive.google.com/file/d/1YCV5jONUYGZRxSOnaXGzA4-oPP61W2Sy/view>`_.

Accessing the clpipe module
-----------------------------

Longleaf modules are a series of software installations and applications that allow users to access programming tools 
or alternate versions of standard packages. If you are a Longleaf user and a member of the rc_hng_psx group, 
clpipe has already been installed for you via the module system. To check if you are a member of the rc_hng_psx group

clpipe is not currently available as part of Longleaf's default module collection.
Instead, it is provided through the UNC Human Neuroimaging Group's module directory, 
which you must setup manually.


Second, make the HNG modules available:

.. code-block:: console

    module use /proj/hng/software/modules

Now save this module source to your default collection:

.. code-block:: console

    module save

You can then use the following to access the latest version of clpipe at any time:

.. code-block:: console

    module add clpipe

Additional module commands
#################

Other basic module commands are provide below.

List all modules on Lonfleaf: 

.. code-block:: console

    module avail

View all your currently loaded modules: 

.. code-block:: console

    module list <modulename>

Remove or unload a loaded module: 

.. code-block:: console

    module rm <modulename>

View all options for a give module: 

.. code-block:: console

    module help <modulename>


Singularity images
#################

Members of the rc_hng_psx group already have access to the latest singularity images for both `fMRIPrep` 
and bids validators at ``/proj/hng/singularity_imgs``, 
so there is no need to construct your own, unless you want a older version.

-----------------------
Python Environment Setup
-----------------------

clpipe requires Python v3.7. If you have the priviledges to add python packages to your system, 
you can install the most recent version of clpipe with:

.. code-block:: console

    pip3 install --upgrade git+https://github.com/cohenlabUNC/clpipe.git

If you don't have access to the global library 
(perhaps you are just a user of an HPC), you can install a local copy by 
adding the ``--user`` flag:

.. code-block:: console

     pip3 install --user --upgrade git+https://github.com/cohenlabUNC/clpipe.git

Pip will automatically install all required Python package dependencies.

-----------------------
External Dependencies
-----------------------

Singularity & Images
-----------------------

clpipe uses Singularity to run certain dependencies as images. clpipe has been
tested against:

- Singularity == v3.2.1

If you are a UNC-CH Longleaf user, Singularity is made available by default when launching
jobs, so you do not need to explicitly add this dependency.

The following programs are required as images:

- fMRIPrep >= v20
- BIDS-validator >= v0.0.0

If you don't already have a Singularity image of fMRIprep, head over to their 
`site <https://fmriprep.readthedocs.io/en/latest/index.html>`_ and follow the 
directions. You will have to change the fMRIprep image path in 
your configuration file.

Similarly, if you do not have a copy of the BIDS-validator Singularity image, 
you'll need to obtain `this image <https://hub.docker.com/r/bids/validator>`_ as well:

Other Dependencies
-----------------------

Additionally, clpipe requires the following tools to be installed in order
to run its postprocessing and analysis steps (UNC-CH Users - this is handled
by the clpipe module):

- FSL >= v6.0.0
- AFNI >= v20.0.00
- R >= v4.0.0

---------------
Batch Languages
---------------

clpipe was originally designed for use on the
University of North Carolina at Chapel Hill's HPC, Longleaf, which uses 
the SLURM task management system. The way clpipe handles what batch language 
to use is through a set of batch configuration files. 
These files are not directly exposed to users, 
and modification of these directly is ill advised. 
For other institutions that use task management systems other than SLURM, 
get in touch with the package maintainers, and we would be happy to 
help setup a configuration file for your system. 
In coming versions of clpipe, functionality will be added to 
allow users to change the batch management system settings.

