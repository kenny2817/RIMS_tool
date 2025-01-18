import json
import os

class Genetica:
    def __init__(self, gene: list):
        self.GENE = gene
        self.SIZE = len(self.GENE)
        self.INDEX = 0
        
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
    
    def reset(self):
        self.INDEX = 0

