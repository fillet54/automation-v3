from flask import  current_app, g
from ..repository import RequirementsRepository, WorkspaceRepository

class Models:
    def __init__(self, config):
        self.config = config

        self.__requirements = None
        self.__workspaces = {} 

    @property
    def requirements(self):
        if not self.__requirements:
            self.__requirements = RequirementsRepository(self.config['DB_PATH'])
        return self.__requirements
    
    def workspace(self, id=0):
        if id not in self.__workspaces:
            self.__workspaces[id] = WorkspaceRepository(id, self.config['DB_PATH'])
        return self.__workspaces[id]

def get_db():
    if 'models' not in g:
        g.models = Models(current_app.config)
    return g.models


