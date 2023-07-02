import os
import pathlib
from datetime import datetime
import re
import inspect
import dill
import jenkins
from tabulate import tabulate

PROJECT = "jobstorm"
SHRDIR = "/home/shared"
IPYTMP = "/ipykernel"
SUFFIX = "tmp_"
PYTBIN = "python3"
PRMNAME = "server.param"
MAXLINE = 100
pattern = re.compile('"([^"]+)"')


class JobResult:
    def __init__(self, output_paramfilepath, job_filename, jobstorm):
        self.output_paramfilepath = output_paramfilepath
        self.job_filename = job_filename
        self.jobstorm = jobstorm
        self.job_number = None
        self.server = jobstorm.server

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
            return "GET_BUILD_INFO_ERROR"
        return build_info["result"]

    def get_result(self):
        status = self.get_status()
        if status not in ["SUCCESS", "UNSTABLE"]:
            raise RuntimeError("job failure or job not finished.")
        return self.jobstorm.loadparam(self.output_paramfilepath)


class JobStorm:
    def __init__(
        self,
        server_url=None,
        username=None,
        password=None,
        shared_dir=SHRDIR,
        project=PROJECT,
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

        if server_url is not None:
            self.server = jenkins.Jenkins(
                server_url, username=username, password=password
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

    def setfunc(self, level=1):
        self.funcs = []
        for i, frame_tuple in enumerate(inspect.stack()):
            if i < level:
                continue
            if i > level:
                break
            for k, v in frame_tuple[0].f_globals.items():
                if inspect.isfunction(v) and IPYTMP in inspect.getfile(v):
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
        filename = f"{SUFFIX}{tss}.py"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)
        self.srcfilepath = filepath
        return filepath

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

    def makefuncjob(self, runfunc, *args, **kwargs):
        if self.srcfilepath is None:
            # error
            return
        tss = datetime.now().strftime("%Y%m%d%H%M%S%f")
        paramfilename = f"{SUFFIX}{tss}.param"
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
        filename = f"{SUFFIX}{tss}_job.py"
        filepath = os.path.join(self.dirpath, filename)
        with open(filepath, "w") as f:
            f.write(src)

        self.server.build_job(self.project, {"job_filename": filename})
        return JobResult(output_paramfilepath, filename, self)

    def create_project(self):
        command = f"{PYTBIN} $job_filename"
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
          <description>job filename</description>
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

    def delete_project(self):
        n_job = len(self.get_job_list())
        if n_job > 0:
            raise RuntimeError("all jobs must be deleted.")
        self.server.delete_job(self.project)

    def find_job(self, job_filename):
        job_info = self.server.get_job_info(self.project)
        for build in job_info["builds"]:
            job_number = build["number"]
            build_info = self.server.get_build_info(self.project, job_number)
            try:
                filename = build_info["actions"][0]["parameters"][0]["value"]
                if job_filename == filename:
                    return job_number
            except:
                pass
        raise RuntimeError("job number not found.")

    def get_job_list(self):
        job_info = self.server.get_job_info(self.project)
        job_list = []
        for build in job_info["builds"]:
            job_number = build["number"]
            build_info = self.server.get_build_info(self.project, job_number)
            result = build_info["result"]
            ts = int(build_info["timestamp"] / 1000)
            dt = datetime.fromtimestamp(ts)
            try:
                filename = build_info["actions"][0]["parameters"][0]["value"]
                filepath = os.path.join(self.dirpath, filename)
                script = open(filepath).readline()
                match = pattern.search(script)
                script_file = match.group(1)
            except:
                script_file = ""
            job_list.append(
                [
                    job_number,
                    dt.strftime("%Y/%m/%d %H:%M:%S"),
                    result,
                    filename,
                    script_file,
                ]
            )
        return job_list

    def print_job_list(self):
        headers = ["job num", "timestamp", "result", "job script", "function script"]
        table = tabulate(
            tabular_data=self.get_job_list(), headers=headers, tablefmt="simple"
        )
        print(table)

    def delete_file(self, filename):
        filepath = os.path.join(self.dirpath, filename)
        try:
            os.remove(filepath)
            print(f"{filepath} is removed.")
        except:
            print(f"{filepath} is not found or some error occurs.")

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
        job_script = job[2]
        func_script = job[3]
        job_name = job_script[0:-7]
        self.delete_file(f"{job_name}_job.py")
        self.delete_file(f"{job_name}.param")
        self.delete_file(f"{job_name}.param.output")
        if not is_same_func_script_exists(job_number, func_script):
            self.delete_file(func_script)
        # self.server.delete_build(self.project, job_number)
        print("delete build job not implemented because of jenkins request error.")
        return
