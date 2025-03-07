from datetime import datetime, timedelta
import simpy # type: ignore
import pm4py # type: ignore
import random
from .process import SimulationProcess
from pm4py.objects.petri_net import semantics # type: ignore
from .parameters import Parameters
from .utility import Prefix
from simpy.events import AnyOf, AllOf, Event # type: ignore
import numpy as np # type: ignore
import copy
import csv
from .utility import Buffer, ParallelObject
from . import custom_function as custom


class Token(object):

    def __init__(self, id: int, net: pm4py.objects.petri_net.obj.PetriNet, am: pm4py.objects.petri_net.obj.Marking, params: Parameters, process: SimulationProcess, prefix: Prefix, type: str, writer: csv.writer, parallel_object: ParallelObject, time: datetime, values=None):
        self._id = id
        self._process = process
        self._start_time = params.START_SIMULATION
        self._params = params
        self._net = net
        self._am = am
        self._prefix = prefix
        self._type = type
        if type == 'sequential':
            self.see_activity = False
        else:
            self.see_activity = True
        self._writer = writer
        self._parallel_object = parallel_object
        self._buffer = Buffer(writer, values)
        self._buffer.set_feature("attribute_case", custom.case_function_attribute(self._id, time))

    def _delete_places(self, places):
        delete = []
        for place in places:
            for p in self._net.places:
                if str(place) in str(p.name):
                    delete.append(p)
        return delete

    def simulation(self, env: simpy.Environment):
        """
            The main function to handle the simulation of a single trace
        """
        trans = self.next_transition(env)
        ### register trace in process ###
        request_resource = None
        resource_trace = self._process._get_resource_trace()
        resource_trace_request = resource_trace.request() if self._type == 'sequential' else None

        while trans is not None:
            if not self.see_activity and self._type == 'sequential':
                yield resource_trace_request
            if type(trans) == list:
                yield AllOf(env, trans)
                am_after = self._parallel_object._get_last_events()
                for d in self._delete_places(self._am):
                    del self._am[d]
                for t in am_after:
                    self._am[t] = 1
                trans = self.next_transition(env)

            if trans and trans.label:
                self._buffer.reset()
                self._buffer.set_feature("id_case", self._id)
                self._buffer.set_feature("activity", trans.label)
                self._buffer.set_feature("prefix", self._prefix.get_prefix(self._start_time + timedelta(seconds=env.now)))
                self._buffer.set_feature("attribute_event", custom.event_function_attribute(self._id, self._start_time + timedelta(seconds=env.now)))

                ### call predictor for waiting time
                if trans.label in self._params.ROLE_ACTIVITY:
                    # genetica_choice = 0
                    # if len(self._params.ROLE_ACTIVITY[trans.label]) > 1: 
                    #     genetica_choice = self._params.GENETICA.next_choice()
                    resource = self._process._get_resource(self._params.ROLE_ACTIVITY[trans.label][0])
                else:
                    raise ValueError('resource/role not defined for this activity', trans.label)

                #self._buffer.set_feature("wip_wait", 0 if type != 'sequential' else resource_trace.count-1)
                self._buffer.set_feature("wip_wait", resource_trace.count)
                self._buffer.set_feature("ro_single", self._process.get_occupations_single_role(resource._get_name()))
                self._buffer.set_feature("ro_total", self._process.get_occupations_all_role())
                self._buffer.set_feature("role", resource._get_name())

                ### register event in process ###
                resource_task = self._process._get_resource_event(trans.label)
                self._buffer.set_feature("wip_activity", resource_task.count)

                queue = 0 if len(resource._queue) == 0 else len(resource._queue[-1])
                self._buffer.set_feature("queue", queue)
                self._buffer.set_feature("enabled_time", self._start_time + timedelta(seconds=env.now))

                waiting = self.define_waiting_time(trans.label)
                if self.see_activity:
                    yield env.timeout(waiting)

                request_resource = resource.request()
                yield request_resource
                single_resource = self._process._set_single_resource(resource._get_name())
                self._buffer.set_feature("resource", single_resource)

                resource_task_request = resource_task.request()
                yield resource_task_request

                ### call predictor for processing time
                self._buffer.set_feature("wip_start", resource_trace.count)
                self._buffer.set_feature("ro_single", self._process.get_occupations_single_role(resource._get_name()))
                self._buffer.set_feature("ro_total", self._process.get_occupations_all_role())
                self._buffer.set_feature("wip_activity", resource_task.count)

                stop = resource.to_time_schedule(self._start_time + timedelta(seconds=env.now))
                yield env.timeout(stop)
                self._buffer.set_feature("start_time", self._start_time + timedelta(seconds=env.now))
                duration = self.define_processing_time(trans.label)

                yield env.timeout(duration)

                self._buffer.set_feature("wip_end", resource_trace.count)
                self._buffer.set_feature("end_time", self._start_time + timedelta(seconds=env.now))

                activity_cost = self.calculate_cost(trans.label, duration, waiting, resource._get_name())
                self._buffer.set_feature("cost", activity_cost)
                
                self._buffer.print_values()
                self._prefix.add_activity(trans.label, resource._get_name(), single_resource)
                resource.release(request_resource)
                self._process._release_single_resource(resource._get_name(), single_resource)
                resource_task.release(resource_task_request)


            self._update_marking(trans)
            trans = self.next_transition(env) if self._am else None

        if self._type == 'parallel':
            self._parallel_object._set_last_events(self._am)
        if self._type == 'sequential':
            resource_trace.release(resource_trace_request)

    def _get_resource_role(self, activity):
        elements = self._params.ROLE_ACTIVITY[activity.label]
        resource_object = []
        for e in elements:
            resource_object.append(self._process._get_resource(e))
        return resource_object

    def _update_marking(self, trans):
        self._am = semantics.execute(trans, self._net, self._am)

    def _delete_tokens(self, name):
        to_delete = []
        for p in self._am:
            if p.name != name:
                to_delete.append(p)
        return to_delete

    def _check_probability(self, prob):
        """Check if the sum of probabilities is 1
        """
        if sum(prob) != 1:
            print('WARNING: The sum of the probabilities associated with the paths is not 1, to run the simulation we define equal probability')
            return False
        else:
            return True

    def _check_type_paths(self, prob):
        if type(prob[0]) is str:
            if sum([x == prob[0] for x in prob]) != len(prob):
                raise ValueError('ERROR: Not all path are defined as same type ', prob)
        elif type(prob[0]) is float:
            if sum([isinstance(x, float) for x in prob]) != len(prob):
                raise ValueError('ERROR: Not all path are defined as same type (float number) ', prob)
        else:
            raise ValueError("ERROR: Invalid input, specify the probability as AUTO, float number or CUSTOM ", prob)

    def _retrieve_check_paths(self, all_enabled_trans):
        prob = []
        for trans in all_enabled_trans:
            try:
                if trans.label:
                    # print(trans.label, end=" | ")
                    prob.append(self._params.PROBABILITY.get(trans.label))
                else:
                    # print(trans.name, " | ", end="")
                    prob.append(self._params.PROBABILITY.get(trans.name))
            except:
                print('ERROR: Not all path probabilities are defined. Define all paths: ', all_enabled_trans)

        return prob

    def define_xor_next_activity(self, all_enabled_trans):
        """ Three different methods to decide which path following from XOR gateway:
        * Random choice: each path has equal probability to be chosen (AUTO)
        ```json
        "probability": {
            "A_ACCEPTED": "AUTO",
            "skip_2": "AUTO",
            "A_FINALIZED": "AUTO",
        }
        ```
        * Defined probability: in the file json it is possible to define for each path a specific probability (PROBABILITY as value)
        ```json
        "probability": {
            "A_PREACCEPTED": 0.20,
            "skip_1": 0.80
        }
        ```
        * Custom method: it is possible to define a dedicate method that given the possible paths it returns the one to
        follow, using whatever techniques the user prefers. (CUSTOM)
        ```json
        "probability": {
            "A_CANCELLED": "CUSTOM",
            "A_DECLINED": "CUSTOM",
            "tauSplit_5": "CUSTOM"
        }
        ```
        """
        prob = ['AUTO'] if not self._params.PROBABILITY else self._retrieve_check_paths(all_enabled_trans)
        # print(prob)
        self._check_type_paths(prob)
        if prob[0] == 'AUTO':
            next = random.choices(list(range(0, len(all_enabled_trans), 1)))[0]
        elif prob[0] == 'CUSTOM':
            next = self.call_custom_xor_function(all_enabled_trans)
        elif prob[0] == 'GENETICA':
            next = self._params.GENETICA.choice(all_enabled_trans)
        elif type(prob[0] == float()):
            if self._check_probability(prob):
                value = [*range(0, len(prob), 1)]
                next = int(random.choices(value, prob)[0])
            else:
                next = random.choices(list(range(0, len(all_enabled_trans), 1)))[0]

        # print("next: ", next)
        # print(all_enabled_trans)
        return all_enabled_trans[next]

    def define_processing_time(self, activity):
        """ Three different methods are available to define the processing time for each activity:
            * Distribution function: specify in the json file the distribution with the right parameters for each
            activity, see the [numpy_distribution](https://numpy.org/doc/stable/reference/random/generator.html) distribution, (DISTRIBUTION).
            **Be careful**: A negative value generated by the distribution is not valid for the simulator.
            ```json
             "task": {
                 "A_FINALIZED": { "name": "uniform", "parameters": { "low": 3600, "high": 7200}},
             }
            ```
            * Custom method: it is possible to define a dedicated method that, given the activity and its
            characteristics, returns the duration of processing time required. (CUSTOM)
            ```json
            "task": {
                 "A_FINALIZED":  { "name": "custom"}
            }
            ```
            * Mixed: It is possible to define a distribution function for some activities and a dedicated method for the others.
            ```json
            "task": {
                 "A_FINALIZED":  { "name": "custom"},
                 "A_REGISTERED":  { "name": "uniform", "parameters": { "low": 3600, "high": 7200}}
            }
            ```
        """
        try:
            if self._params.TASKS[activity]["attributes"]["distribution"] == 'custom':
                duration = self.call_custom_processing_time()
            else:
                distribution = self._params.TASKS[activity]["attributes"]["distribution"]
                parameters = self._params.TASKS[activity]["attributes"]["parameters"]
                duration = getattr(np.random, distribution)(**parameters, size=1)[0]
                if duration < 0:
                    # print("WARNING: Negative processing time",  duration)
                    duration = 0
        except:
            raise ValueError("ERROR: The processing time of", activity, "is not defined in json file")
        return duration

    def define_waiting_time(self, next_act):
        """ Three different methods are available to define the waiting time before each activity:
            * Distribution function: specify in the json file the distribution with the right parameters for each
            activity, see the [numpy_distribution](https://numpy.org/doc/stable/reference/random/generator.html) distribution, (DISTRIBUTION).
            **Be careful**: A negative value generated by the distribution is not valid for the simulator.
            ```json
             "waiting_time": {
                 "A_PARTLYSUBMITTED":  { "name": "uniform", "parameters": { "low": 3600, "high": 7200}}
             }
            ```
            * Custom method: it is possible to define a dedicated method that, given the next activity with its
            features, returns the duration of waiting time. (CUSTOM)
            ```json
            "waiting_time": {
                 "A_PARTLYSUBMITTED": { "name": "custom"}
            }
            ```
            * Mixed: As the processing time, it is possible to define a mix of methods for each activity.
            ```json
            "waiting_time": {
                 "A_PARTLYSUBMITTED":  { "name": "custom"},
                 "A_APPROVED":  { "name": "uniform", "parameters": { "low": 3600, "high": 7200}}
            }
            ```
        """
        try:
            if self._params.WAITING_TIME[next_act]["name"] == 'custom':
                duration = self.call_custom_waiting_time()
            else:
                distribution = self._params.WAITING_TIME[next_act]['name']
                parameters = self._params.WAITING_TIME[next_act]['parameters']
                duration = getattr(np.random, distribution)(**parameters, size=1)[0]
                if duration < 0:
                    print("WARNING: Negative waiting time",  duration)
                    duration = 0
        except:
            duration = 0

        return duration

    def call_custom_processing_time(self):
        """
        Call to the custom functions in the file *custom_function.py*.
        """
        return custom.custom_processing_time(self._buffer)

    def call_custom_waiting_time(self):
        """
            Call to the custom functions in the file *custom_function.py*.
        """
        return custom.custom_waiting_time(self._buffer)

    def call_custom_xor_function(self, all_enabled_trans):
        """
            Call to the custom functions in the file *custom_function.py*.
        """
        return custom.custom_decision_mining(self._buffer)

    def next_transition(self, env):
        """
        Method to define the next activity in the petrinet.
        """
        all_enabled_trans = semantics.enabled_transitions(self._net, self._am)
        all_enabled_trans = list(all_enabled_trans)
        all_enabled_trans.sort(key=lambda x: x.name)
        if len(all_enabled_trans) == 0:
            return None
        elif len(all_enabled_trans) == 1:
            return all_enabled_trans[0]
        else:
            if len(self._am) == 1:
                token_name = self._am
                # print("token name: ",token_name)
                return self.define_xor_next_activity(all_enabled_trans)
            else:
                events = []
                for token in self._am:
                    name = token.name
                    new_am = copy.copy(self._am)
                    tokens_to_delete = self._delete_tokens(name)
                    for p in tokens_to_delete:
                        del new_am[p]
                    path = env.process(Token(self._id, self._net, new_am, self._params, self._process, self._prefix, "parallel", self._writer, self._parallel_object, self._buffer._get_dictionary()).simulation(env))
                    events.append(path)
                return events
    
    def calculate_cost(self, activity, duration, waiting, resource_name):
        """
        Calculate the cost associated with a specific activity.
        """
        base_cost = self._params.TASKS[activity].get('base_cost', 0)
        total_cost = base_cost + (duration + waiting) * self._params.ROLE_CAPACITY[resource_name][2]
        return total_cost

