import os
import pathlib
from datetime import datetime
import re
import inspect
import dill
import jenkins
from jenkins.__init__ import DELETE_BUILD
from tabulate import tabulate
from urllib.parse import urljoin
import requests

PROJECT = "jobstorm"
SHRDIR = "/home/shared"
IPYTMP = ["/ipykernel", "ipython-input"]
PREFIX = "tmp_"
JOBCMD = "python3"
PYTCMD = "python3"
SAGCMD = "sage"
PRMNAME = "server.param"
MAXLINE = 100
func_script_pattern = re.compile('"([^"]+)"')
tmp_pattern = re.compile("(tmp_[^_]+)")


class JobResult:
    def __init__(self, output_paramfilepath, job_filename, jobstorm):
        self.output_paramfilepath = output_paramfilepath
        self.job_filename = job_filename
        self.jobstorm = jobstorm
        self.job_number = None
        self.server = jobstorm.server
        job_prefix = jobstorm.get_job_prefix(job_filename)
        message_filename = job_prefix + ".message"
        self.message_filepath = os.path.join(jobstorm.dirpath, message_filename)

    def get_job_number(self):
        if self.job_number is None:
            self.job_number = self.jobstorm.find_job(self.job_filename)
        return self.job_number

    def get_status(self):
        project = self.jobstorm.project
        try:
            build_info = self.server.get_build_info(project, self.get_job_number())
            if build_info["result"] is None:
                raise RuntimeError()
        except:
            return "JOB_WAITING_IN_QUEUE"
        return build_info["result"]

    def get_result(self):
        status = self.get_status()
        if status not in ["SUCCESS", "UNSTABLE"]:
            raise RuntimeError("job failure or job not finished.")
        return self.jobstorm.loadparam(self.output_paramfilepath)

    def set_message(self, message):
        f = open(self.message_filepath, "w")
        f.write(message)
        f.close()

    def get_message(self):
        try:
            f = open(self.message_filepath)
            message = f.readline()
            f.close()
        except:
            message = ""
        return message


class JobStormBase:
    """Job generator.

    Constructor options
    -------------------
    server_url : str
        URL of Jenkins.
    username : str
        Jenkins username.
    password : str
        Jenkins password.
    shared_dir : str
        root directory path of job workspace.
    project : str
        Jenkins project name.
    job_cmd : str
        command to run script.
    server_timeout : str
        timeout setting for Jenkins server.
    """

    def __init__(
        self,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        job_cmd=JOBCMD,
        server_timeout=60,
    ):
        if shared_dir is None:
            raise ValueError("shared_dir must be set.")
        if project is None:
            raise ValueError("project must be set.")
        if not pathlib.Path(shared_dir).is_absolute():
            raise ValueError("shared_dir must be absolute path.")
        if not os.path.isdir(shared_dir):
            raise ValueError("shared_dir must be dir path.")

        self.shared_dir = shared_dir
        self.project = project
        self.dirpath = os.path.join(shared_dir, self.project)
        if os.path.isdir(self.dirpath):
            print(f"{self.dirpath} already exists.")
        else:
            os.makedirs(self.dirpath, exist_ok=True)
            os.chmod(self.dirpath, 0o0777)

        self.codes = []
        self.funcs = []
        self.srcfilepath = None
        self.job_cmd = job_cmd
        self.server_timeout = server_timeout

        if server_url is not None:
            self.server = jenkins.Jenkins(
                server_url,
                username=username,
                password=password,
                timeout=self.server_timeout,
            )
            me = self.server.get_whoami()
            if me["fullName"] is None:
                raise RuntimeError("authentication failed.")
            setup = {
                "server_url": server_url,
                "username": username,
                "password": password,
            }
            param_path = os.path.join(self.dirpath, PRMNAME)
            setup = self.saveparam(param_path, setup)
        else:
            param_path = os.path.join(self.dirpath, PRMNAME)
            setup = self.loadparam(param_path)
            self.server = jenkins.Jenkins(
                setup["server_url"],
                username=setup["username"],
                password=setup["password"],
                timeout=self.server_timeout,
            )
            me = self.server.get_whoami()
            if me["fullName"] is None:
                raise RuntimeError("authentication failed.")
        try:
            xmlstr = self.server.get_job_config(self.project)
            if xmlstr is None:
                raise RuntimeError()
        except:
            print(f"project (name={self.project}) is not created.")
            print("please create project by create_project().")

    def setcode(self):
        for i, frame_tuple in enumerate(inspect.stack(context=MAXLINE + 1)):
            if i == 0:
                continue
            if i > 1:
                break
            cc = frame_tuple.code_context
            if cc is None:
                return
            if cc.count("\n") + 1 > MAXLINE:
                raise RuntimeError("code size must be <= {MAXLINE}.")
            self.codes.extend(cc)

    def getcode(self):
        codes = ""
        for code in self.codes:
            codes += code
        return codes

    def _is_ipy_tmp(self, filepath):
        for ipy_tmp in IPYTMP:
            if ipy_tmp in filepath:
                return True
        return False

    def setfunc(self, level=1):
        self.funcs = []
        for i, frame_tuple in enumerate(inspect.stack()):
            if i < level:
                continue
            if i > level:
                break
            for k, v in frame_tuple[0].f_globals.items():
                if inspect.isfunction(v) and self._is_ipy_tmp(inspect.getfile(v)):
                    self.funcs.append(v.__name__)

    def getfunc(self):
        funcs = []
        for func_name in self.funcs:
            func = self.retrieve(func_name)
            if func is None:
                continue
            funcs.append(func)

        codes = ""
        for code in funcs:
            codes += code
        return codes

    def retrieve(self, name):
        for frame_tuple in inspect.stack():
            d = frame_tuple[0].f_globals
            k = d.keys()
            if not name in k:
                continue
            v = d[name]
            if inspect.isfunction(v):
                return inspect.getsource(v)
        return None

    def saveparam(self, filename, params):
        fout = open(filename, "wb")
        dill.dump(params, fout)
        fout.close()

    def loadparam(self, filename):
        fin = open(filename, "rb")
        data = dill.load(fin)
        fin.close()
        return data

    def create_project(self):
        command = f"$job_cmd $job_filename"
        xmlstr = f"""<?xml version='1.1' encoding='UTF-8'?>
<project>
  <actions/>
  <description></description>
  <keepDependencies>false</keepDependencies>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.TextParameterDefinition>
          <name>job_filename</name>
          <description>job filename</description>
          <trim>false</trim>
        </hudson.model.TextParameterDefinition>
        <hudson.model.TextParameterDefinition>
          <name>dirpath_of_workspace</name>
          <defaultValue>{self.dirpath}</defaultValue>
          <description>job workspace</description>
          <trim>false</trim>
        </hudson.model.TextParameterDefinition>
        <hudson.model.TextParameterDefinition>
          <name>job_cmd</name>
          <defaultValue>{self.job_cmd}</defaultValue>
          <description>job command</description>
          <trim>false</trim>
        </hudson.model.TextParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
  <scm class="hudson.scm.NullSCM"/>
  <canRoam>true</canRoam>
  <disabled>false</disabled>
  <blockBuildWhenDownstreamBuilding>false</blockBuildWhenDownstreamBuilding>
  <blockBuildWhenUpstreamBuilding>false</blockBuildWhenUpstreamBuilding>
  <triggers/>
  <concurrentBuild>false</concurrentBuild>
  <builders>
    <hudson.tasks.Shell>
      <command>cd $dirpath_of_workspace
{command}</command>
      <configuredLocalRules/>
    </hudson.tasks.Shell>
  </builders>
  <publishers/>
  <buildWrappers/>
</project>"""
        self.server.create_job(self.project, xmlstr)
        print(f"project (name={self.project}) is created.")

    def delete_project(self):
        n_job = len(self.get_job_list())
        if n_job > 0:
            raise RuntimeError("all jobs must be deleted.")
        self.server.delete_job(self.project)

    def find_job(self, job_filename):
        job_info = self.server.get_job_info(self.project)
        for build in job_info["builds"]:
            job_number = build["number"]
            try:
                build_info = self.server.get_build_info(self.project, job_number)
                filename = build_info["actions"][0]["parameters"][0]["value"]
                if job_filename == filename:
                    return job_number
            except:
                pass
        raise RuntimeError("job number not found.")

    def get_job(self, job_number, info="detail"):
        def get_filename(build_info):
            try:
                filename = build_info["actions"][0]["parameters"][0]["value"]
            except:
                filename = None
            return filename

        def get_script_file(filename):
            script_file = ""
            if not filename:
                return script_file
            try:
                filepath = os.path.join(self.dirpath, filename)
                f = open(filepath)
                script = f.readline()
                f.close()
                match = func_script_pattern.search(script)
                script_file = match.group(1)
            except:
                pass
            return script_file

        def get_message(filename):
            message = ""
            if not filename:
                return message
            try:
                job_prefix = self.get_job_prefix(filename)
                message_filename = job_prefix + ".message"
                message_filepath = os.path.join(self.dirpath, message_filename)
                f = open(message_filepath)
                message = f.readline()
                f.close()
            except:
                pass
            return message

        try:
            build_info = self.server.get_build_info(self.project, job_number)
            result = build_info["result"]
            ts = int(build_info["timestamp"] / 1000)
            dt = datetime.fromtimestamp(ts)
            filename = get_filename(build_info)
            message = get_message(filename)
        except:
            return None

        if info != "simple":
            script_file = get_script_file(filename)
        job_elem = [
            job_number,
            dt.strftime("%Y/%m/%d %H:%M:%S"),
            result,
            message,
        ]
        if info != "simple":
            job_elem.extend(
                [
                    filename,
                    script_file,
                ]
            )
        return job_elem

    def get_job_list(self, info="detail"):
        job_info = self.server.get_job_info(self.project)
        job_list = []
        for build in job_info["builds"]:
            job_number = build["number"]
            job = self.get_job(job_number, info=info)
            if job is None:
                continue
            job_list.append(job)
        return job_list

    def get_job_prefix(self, job_filename):
        match = tmp_pattern.search(job_filename)
        return match.group(1)

    def get_jobresult(self, job_number):
        try:
            build_info = self.server.get_build_info(self.project, job_number)
            filename = build_info["actions"][0]["parameters"][0]["value"]
            job_prefix = self.get_job_prefix(filename)
            output_paramfilename = job_prefix + ".param.output"
            output_paramfilepath = os.path.join(self.dirpath, output_paramfilename)
            return JobResult(output_paramfilepath, filename, self)
        except:
            return None

    def print_job_list(self, max_cols=None, info="simple"):
        job_list = self.get_job_list(info=info)
        headers = ["job num", "timestamp", "result", "message"]
        if info != "simple":
            headers.extend(
                [
                    "job script",
                    "function script",
                ]
            )
        table = tabulate(
            tabular_data=job_list[0:max_cols], headers=headers, tablefmt="simple"
        )
        print(table)

    def delete_file(self, filename):
        filepath = os.path.join(self.dirpath, filename)
        try:
            os.remove(filepath)
            print(f"{filepath} is removed.")
        except:
            print(f"{filepath} is not found or some error occurs.")

    def server_delete_build(self, job_number):
        # workaround
        param = self.server._get_job_folder(self.project)
        url_path = DELETE_BUILD % (
            {"folder_url": param[0], "short_name": param[1], "number": job_number}
        )
        url = str(urljoin(self.server.server, url_path))
        req = requests.Request("POST", url)
        self.server.jenkins_request(req, True, True).text


class JobStormPython(JobStormBase):
    def __init__(
        self,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        job_cmd=PYTCMD,
        server_timeout=60,
    ):
        super().__init__(
            server_url,
            username,
            password,
            shared_dir,
            project,
            job_cmd,
            server_timeout,
        )

    def savefunc(self):
        self.setfunc(level=2)
        src = self.getcode()
        src += "\n"
        src += "\n"
        src += "from jobstorm import *\n"
        src += f'jobstorm = JobStorm(shared_dir="{self.shared_dir}", project="{self.project}")\n'
        src += "\n"
        src += "\n"
        src += self.getfunc()
        tss = datetime.now().strftime("%Y%m%d%H%M%S%f")
        filename = f"{PREFIX}{tss}.py"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)
        self.srcfilepath = filepath
        return filepath

    def makefuncjob(self, runfunc, *args, **kwargs):
        if self.srcfilepath is None:
            # error
            return
        tss = datetime.now().strftime("%Y%m%d%H%M%S%f")
        paramfilename = f"{PREFIX}{tss}.param"
        paramfilepath = os.path.join(self.dirpath, paramfilename)
        self.saveparam(paramfilepath, [args, kwargs])
        output_paramfilepath = f"{paramfilepath}.output"

        srcfile = os.path.basename(self.srcfilepath)

        if inspect.isfunction(runfunc):
            runfuncname = runfunc.__name__
        else:
            runfuncname = runfunc

        src = f'exec(open("{srcfile}").read())\n'
        src += "def run_jobcode():\n"
        src += f'    params = jobstorm.loadparam("{paramfilepath}")\n'
        src += f"    output = {runfuncname}(*params[0], **params[1])\n"
        src += f'    jobstorm.saveparam("{output_paramfilepath}", output)\n'
        src += "\n"
        src += "run_jobcode()\n"
        filename = f"{PREFIX}{tss}_job.py"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)

        self.server.build_job(
            self.project, {"job_filename": filename, "job_cmd": self.job_cmd}
        )
        return JobResult(output_paramfilepath, filename, self)

    def delete_job(self, job_number):
        def is_same_func_script_exists(job_number, func_script):
            for k, v in job_dict.items():
                if k == job_number:
                    continue
                if func_script == v[3]:
                    return True
            return False

        job_list = self.get_job_list()
        job_dict = {job[0]: job[1:] for job in job_list}
        job = job_dict.get(job_number)
        if job is None:
            print(f"job ({job_number}) is not found.")
            return
        job_script = job[3]
        func_script = job[4]
        job_name = job_script[0:-7]
        self.delete_file(f"{job_name}_job.py")
        self.delete_file(f"{job_name}.param")
        self.delete_file(f"{job_name}.param.output")
        self.delete_file(f"{job_name}.message")
        if not is_same_func_script_exists(job_number, func_script):
            self.delete_file(func_script)
        # self.server.delete_build(self.project, job_number)
        self.server_delete_build(job_number)
        return


class JobStormSage(JobStormBase):
    def __init__(
        self,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        job_cmd=SAGCMD,
        server_timeout=60,
    ):
        super().__init__(
            server_url,
            username,
            password,
            shared_dir,
            project,
            job_cmd,
            server_timeout,
        )

    def savefunc(self):
        self.setfunc(level=2)
        src = self.getcode()
        src += "\n"
        src += "\n"
        src += "from jobstorm import *\n"
        src += f'jobstorm = JobStorm(shared_dir="{self.shared_dir}", project="{self.project}")\n'
        src += "\n"
        src += "\n"
        src += "def Integer(x):\n"
        src += "    return x\n"
        src += "\n"
        src += "\n"
        src += "def RealNumber(x):\n"
        src += "    return x\n"
        src += "\n"
        src += "\n"
        src += self.getfunc()
        tss = datetime.now().strftime("%Y%m%d%H%M%S%f")
        filename = f"{PREFIX}{tss}.sage"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)
        self.srcfilepath = filepath
        return filepath

    def makefuncjob(self, runfunc, *args, **kwargs):
        if self.srcfilepath is None:
            # error
            return
        tss = datetime.now().strftime("%Y%m%d%H%M%S%f")
        paramfilename = f"{PREFIX}{tss}.param"
        paramfilepath = os.path.join(self.dirpath, paramfilename)
        self.saveparam(paramfilepath, [args, kwargs])
        output_paramfilepath = f"{paramfilepath}.output"

        srcfile = os.path.basename(self.srcfilepath)

        if inspect.isfunction(runfunc):
            runfuncname = runfunc.__name__
        else:
            runfuncname = runfunc

        src = f'load("{srcfile}")\n'
        src += "def run_jobcode():\n"
        src += f'    params = jobstorm.loadparam("{paramfilepath}")\n'
        src += f"    output = {runfuncname}(*params[0], **params[1])\n"
        src += f'    jobstorm.saveparam("{output_paramfilepath}", output)\n'
        src += "\n"
        src += "run_jobcode()\n"
        filename = f"{PREFIX}{tss}_job.sage"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)

        self.server.build_job(
            self.project, {"job_filename": filename, "job_cmd": self.job_cmd}
        )
        return JobResult(output_paramfilepath, filename, self)

    def delete_job(self, job_number):
        def is_same_func_script_exists(job_number, func_script):
            for k, v in job_dict.items():
                if k == job_number:
                    continue
                if func_script == v[3]:
                    return True
            return False

        job_list = self.get_job_list()
        job_dict = {job[0]: job[1:] for job in job_list}
        job = job_dict.get(job_number)
        if job is None:
            print(f"job ({job_number}) is not found.")
            return
        job_script = job[3]
        func_script = job[4]
        job_name = job_script[0:-7]
        self.delete_file(f"{job_name}_job.sage")
        self.delete_file(f"{job_name}.param")
        self.delete_file(f"{job_name}.param.output")
        self.delete_file(f"{job_name}.message")
        if not is_same_func_script_exists(job_number, func_script):
            self.delete_file(func_script)
        # self.server.delete_build(self.project, job_number)
        self.server_delete_build(job_number)
        return


class JobStorm(JobStormPython):
    def __init__(
        self,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        python_cmd=PYTCMD,
        server_timeout=60,
    ):
        super().__init__(
            server_url,
            username,
            password,
            shared_dir,
            project,
            python_cmd,
            server_timeout,
        )

    @classmethod
    def python(
        cls,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        job_cmd=PYTCMD,
        server_timeout=60,
    ):
        return JobStormPython(
            server_url,
            username,
            password,
            shared_dir,
            project,
            job_cmd,
            server_timeout,
        )

    @classmethod
    def sage(
        cls,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
        job_cmd=SAGCMD,
        server_timeout=60,
    ):
        return JobStormSage(
            server_url,
            username,
            password,
            shared_dir,
            project,
            job_cmd,
            server_timeout,
        )
