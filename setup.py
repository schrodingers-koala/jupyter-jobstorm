from setuptools import setup
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Github README.md
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="jupyter-jobstorm",
    packages=["jobstorm"],
    version="0.1.2",
    license="MIT",
    install_requires=["dill", "python-jenkins", "tabulate"],
    author="schrodingers-koala",
    author_email="schrodingers.koala@gmail.com",
    url="https://github.com/schrodingers-koala/jupyter-jobstorm",
    description="A tool to run a function written in Jupyter cell as a job",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="jupyter-jobstorm jobstorm",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
    ],
)
