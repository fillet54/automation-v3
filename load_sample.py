from automationv2.repository import RequirementsRepository, import_requirements_from_file

repo = RequirementsRepository('requirements.db')
import_requirements_from_file('test/data/sample_requirements.txt', repo)

