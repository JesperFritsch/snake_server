import requests

class Job:
    def __init__(self, language, version, files, stdin=None, args=None):
        self.language = language
        self.version = version
        self.files = files
        self.stdin = stdin
        self.args = args
        
    def to_dict(self):
        return {
            "language": self.language,
            "version": self.version,
            "files": self.files,
            "stdin": self.stdin,
            "args": self.args
        }

class PistonHandler:
    def __init__(self, base_url):
        self.base_url = base_url

    def execute(self, job):
        url = f"{self.base_url}/api/v2/execute"
        payload = job.to_dict()
        response = requests.post(url, json=payload)
        return response.json()

    def execute_multiple(self, jobs):
        url = f"{self.base_url}/api/v2/execute-multiple"
        payload = {"jobs": jobs}
        response = requests.post(url, json=payload)
        return response.json()

    def get_runtimes(self):
        url = f"{self.base_url}/api/v2/runtimes"
        response = requests.get(url)
        return response.json()

    def get_packages(self):
        url = f"{self.base_url}/api/v2/packages"
        response = requests.get(url)
        return response.json()

    def install_package(self, language, version):
        url = f"{self.base_url}/api/v2/packages"
        payload = {"language": language, "version": version}
        response = requests.post(url, json=payload)
        return response.json()

    def uninstall_package(self, language, version):
        url = f"{self.base_url}/api/v2/packages"
        payload = {"language": language, "version": version}
        response = requests.delete(url, json=payload)
        return response.json()
