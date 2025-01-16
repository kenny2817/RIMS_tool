import json
import os

class Genetica:
    def __init__(self, path_genetica: str):
        self.PATH_GENETICA = path_genetica
        if path_genetica != 'NULL':
            self.INDEX = 0
            self.read_metadata_file()
    
    def read_metadata_file(self):
        '''
        Method to read genetic algorithm choice
        '''
        if os.path.exists(self.PATH_GENETICA):
            with open(self.PATH_GENETICA, "r") as file:
                file.seek(0, 2)
                file.seek(file.tell() - 2, 0)
                while file.read(1) != '\n':
                    file.seek(file.tell() - 2, 0)
                last_line = file.readline().strip()

            data = json.loads(last_line)
            self.ID = data['solution_id']
            self.GENE = data['genes']
            self.RESOURCE_ASSIGNMENT = data['resource_assignment']
            self.SIZE = len(self.GENE)
        else:
            raise ValueError('Genetica file does not exist')
        
    def next_choice(self):
        if (self.INDEX < self.SIZE):
            data = self.GENE[self.INDEX]
            self.INDEX += 1
            return data
        else:
            raise ValueError('Too many decison points, gene too short: i = ' + str(self.INDEX) + ', size = ' + str(self.SIZE))
    
    def next_resource(self):
        if (self.INDEX < self.SIZE):
            resource = self.RESOURCE_ASSIGNMENT[self.INDEX]
            self.INDEX += 1
            return resource
        else:
            raise ValueError('Too many decison points, gene too short')
        
    def send_result(self, duration, cost):
        jsonl_path = self.PATH_GENETICA
        with open(jsonl_path, "a") as jsonl:
            jsonl.write(json.dumps({"results": [duration, cost]}) + "\n")
    
    def reset(self):
        self.INDEX = 0

