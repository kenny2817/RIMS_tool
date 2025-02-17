import json
import os

class Genetica:
    def __init__(self, gene: list, number_traces: int):
        self.GENE = gene
        self.SIZE = len(self.GENE)
        self.trace_decision_points = self.SIZE // number_traces

        self.current_trace = 0

    def set_mapping(self, mapping: dict[str: int]):
        self.mapping = mapping

    def next_trace(self):
        self.current_trace += self.trace_decision_points

    def choice(self, all_trans: list) -> int:
        try:
            gene_index = self.mapping.get(all_trans[0]) or 0
            return self.GENE[self.current_trace + gene_index]
        except:
            raise ValueError(f"a decision point is not correctely defined: out of bounds")

    def reset(self):
        self.current_trace = 0

