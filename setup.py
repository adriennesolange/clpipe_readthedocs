from setuptools import setup, find_packages
from clpipe.config.package import *

if __name__ == "__main__":
      setup(
            name=PACKAGE_NAME,
            version=VERSION,
            description=DESCRIPTION,
            url=REPO_URL,
            author=AUTHORS,
            author_email=AUTHOR_EMAIL,
            license=LICENSE,
            python_requires=PYTHON_REQUIRES,
            install_requires=INSTALL_REQUIRES,
            include_package_data=True,
            packages=find_packages(),
            package_data=PACKAGE_DATA,
            entry_points=ENTRY_POINTS,
            zip_safe=False
      )
