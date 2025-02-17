"""
    Class for reading simulation parameters
"""
import json
import math
import os
from datetime import datetime
from .genetica import Genetica

class Parameters(object):

    def __init__(self, path_parameters: str, gene: list, traces: int):
        self.GENETICA = Genetica(gene, traces)
        self.TRACES = traces
        """TRACES: number of traces to generate"""
        self.PATH_PARAMETERS = path_parameters
        """PATH_PARAMETERS: path of json file for others parameters. """
        self.read_metadata_file()
        
    def read_metadata_file(self):
        '''
        Method to read parameters from json file, see *main page* to get the whole list of simulation parameters.
        '''
        if os.path.exists(self.PATH_PARAMETERS):
            with open(self.PATH_PARAMETERS) as file:
                data = json.load(file)
                self.START_SIMULATION = self._check_default_parameters(data, 'start_timestamp')
                self.SIM_TIME = self._check_default_parameters(data, 'duration_simulation')
                self.PROBABILITY = data['probability'] if 'probability' in data.keys() else []
                self.GENETICA.set_mapping(data['mapping'] if 'mapping' in data.keys() else {})
                self.TASKS = data['tasks']
                self.WAITING_TIME = data['waiting_time'] if 'waiting_time' in data.keys() else []
                self.INTER_TRIGGER = data["interTriggerTimer"]
                self.ROLE_ACTIVITY = dict()
                
                for name, elem in self.TASKS.items():
                    role = elem['roles']
                    if not isinstance(role, list):  # list assert
                        role = [role]
                    self.ROLE_ACTIVITY[name] = role

                if 'calendar' in data['interTriggerTimer'] and data['interTriggerTimer']['calendar']:
                    self.ROLE_CAPACITY = {'TRIGGER_TIMER': [math.inf, {'days': data['interTriggerTimer']['calendar']['days'], 'hour_min': data['interTriggerTimer']['calendar']['hour_min'], 'hour_max': data['interTriggerTimer']['calendar']['hour_max']}]}
                else:
                    self.ROLE_CAPACITY = {'TRIGGER_TIMER': [math.inf, []]}
                self._define_roles_resources(data['roles'])
        else:
            raise ValueError(f"Parameter file does not exist {self.PATH_PARAMETERS}")

    def _define_roles_resources(self, roles):
        for idx, key in enumerate(roles):
            self.ROLE_CAPACITY[key] = [roles[key]['resources'], 
                                       {'days': roles[key]['attributes']['calendar']['days'],
                                        'hour_min': roles[key]['attributes']['calendar']['hour_min'],
                                        'hour_max': roles[key]['attributes']['calendar']['hour_max']},
                                       roles[key]['attributes']['salary']]

    def _check_default_parameters(self, data, type):
        if type == 'start_timestamp':
            value = datetime.strptime(data['start_timestamp'], '%Y-%m-%d %H:%M:%S') if type in data else datetime.now()
        elif type == 'duration_simulation':
            value = data['duration_simulation']*86400 if type in data else 31536000
        return value