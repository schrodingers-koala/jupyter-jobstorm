# Jupyter-JobStorm

JupyterLab is a wonderful development environment for notebooks.
By using JupyterLab, you can run a Python program easily.
In a notebook, you can run a code and get the output directly below the code cell.
In case of quick code execution and fast response, it becomes a wonderful development experience.
Waiting about one minute for the response would be fine for almost everyone.
If it takes several minutes for executing a code, how do you spend your time?
You may use time to code for the next execution, chat or have a coffee.
But, do you want to run your codes any time and get results later?

Jupyter-JobStorm is a solution for executing your codes asynchronously.
Jupyter-JobStorm generates a job for a code to run and requests Jenkins to run the job.
You can check the job status and get the result through Jupyter-JobStorm.
Please see examples for details.

I believe that Jenkins will catch and execute jobs which are sent from you like the mighty storm on the planet Jupiter.

## Feature

- Supporting Jenkins as job runner
- Running a function (\*) of Python/SageMath script as a job
- Retrieving the status and the result of the job

(\*) Currently only variables of function arguments are passed to the function and variables outside of the function are not supported.

## Requirement

- dill >= 0.3.5.1
- python-jenkins >= 1.8.0
- tabulate >= 0.9.0
- Jenkins
- Jupyter
- Shared directory accessible to Jupyter server and Jenkins nodes.

## Installation

Installations required for Jupyter server and Jenkins nodes.

```console
$ pip install jupyter-jobstorm
```

## Usage

- [Example 1: Python Job Test](https://github.com/schrodingers-koala/jupyter-jobstorm/blob/main/example/job_test.ipynb)

- [Example 2: Sage Job Test](https://github.com/schrodingers-koala/jupyter-jobstorm/blob/main/example/sage_job_test.ipynb)

- [Example 3: Job Management Test](https://github.com/schrodingers-koala/jupyter-jobstorm/blob/main/example/job_management.ipynb)

## License

Jupyter-JobStorm is under MIT license.
