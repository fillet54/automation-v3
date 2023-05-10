from .requirements import *
from .workspace import *
from .testcase import *

def import_requirements_from_file(file_path, repository):
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            idx = line.rfind("[")
            requirement_text = line[:idx].strip()
            requirement_id = line[idx + 1:-2].strip()
            subsystem = requirement_id.split("VMC")[1].split("0")[0].strip()
            requirement = Requirement(requirement_id, requirement_text, subsystem)
            print(requirement_text, requirement_id, subsystem)
            repository.add(requirement)
