from datetime import timedelta
import simpy
import pm4py
import random
from process import SimulationProcess
from pm4py.objects.petri_net import semantics
from simpy.events import AnyOf, AllOf, Event
import numpy as np
import copy
from utility import Buffer


class Token(object):

    def __init__(self, id, net, am, params, process: SimulationProcess, prefix, type, writer):
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

    def _delete_places(self, places):
        delete = []
        for place in places:
            for p in self._net.places:
                if str(place) in str(p.name):
                    delete.append(p)
        return delete

    def simulation(self, env: simpy.Environment):
        trans = self.next_transition(env)
        ### register trace in process ###
        resource_trace = self._process.get_resource_trace()
        resource_trace_request = resource_trace.request()

        while trans is not None:
            buffer = Buffer(self._writer)
            #buffer.write_columns()
            if self.see_activity:
                yield resource_trace_request
            if type(trans) == list:
                #print(trans)
                self._process.get_last_events()
                #yield AllOf(env, trans)
                yield trans[0] & trans[1]
                am_after = self._process.get_last_events() - set(self._am)
                for d in self._delete_places(self._am):
                    del self._am[d]
                for t in am_after:
                    self._am[t] = 1
                #pm4py.view_petri_net(self._net, self._am)
                all_enabled_trans = list(semantics.enabled_transitions(self._net, self._am))
                trans = all_enabled_trans[0]

            if trans.label is not None:
                buffer.set_feature("id_case", self._id)
                buffer.set_feature("activity", trans.label)
                buffer.set_feature("prefix", self._prefix.get_prefix())
                self._prefix.add_activity(trans.label)

                ### call predictor for waiting time
                if trans.label in self._params.ROLE_ACTIVITY:
                    resource = self._process.get_resource(self._params.ROLE_ACTIVITY[trans.label])
                else:
                    raise ValueError('Not resource/role defined for this activity', trans.label)

                buffer.set_feature("wip_wait", resource_trace.count)
                buffer.set_feature("ro_single", self._process.get_occupations_single_resource(resource.get_name()))

                queue = 0 if len(resource.queue) == 0 else len(resource.queue[-1])
                buffer.set_feature("queue", queue)

                waiting = 5

                if self.see_activity:
                    yield env.timeout(waiting)

                request_resource = resource.request()
                buffer.set_feature("enabled_time", str(self._start_time + timedelta(seconds=env.now)))
                yield request_resource

                ### register event in process ###
                resource_task = self._process.get_resource_event(trans.name)
                resource_task_request = resource_task.request()
                yield resource_task_request

                buffer.set_feature("start_time", str(self._start_time + timedelta(seconds=env.now)))
                ### call predictor for processing time
                buffer.set_feature("wip_start", resource_trace.count)
                buffer.set_feature("ro_single", self._process.get_occupations_single_resource(resource.get_name()))
                buffer.set_feature("wip_activity", resource_task.count)

                duration = np.random.uniform(3600, 7200)

                yield env.timeout(duration)

                buffer.set_feature("wip_end", resource_trace.count)
                buffer.set_feature("end_time", str(self._start_time + timedelta(seconds=env.now)))
                buffer.set_feature("role", resource.get_name())
                buffer.print_values()
                resource.release(request_resource)
                resource_task.release(resource_task_request)

            self._update_marking(trans)
            trans = self.next_transition(env)

        if self._type == 'parallel':
            self._process.set_last_events(self._am)
        resource_trace.release(resource_trace_request)

    def _update_marking(self, trans):
        self._am = semantics.execute(trans, self._net, self._am)

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
        list_trans = [trans.name for trans in all_enabled_trans]
        try:
            prob = [self._params.PROBABILITY[key] for key in list_trans]

        except:
            print('ERROR: Not all path probabilities are defined. Define all paths: ', list_trans)
        return prob

    def define_xor_next_activity(self, all_enabled_trans):
        """ Three different methods to decide which path following from XOR gateway:
        * Random choice: each path has equal probability to be chosen (AUTO)
        * Defined probability: in the file json it is possible to define for each path a specific probability (PROBABILITY as value)
        * Ad-hoc method: it is possible to define a dedicate method that given the possible paths it returns the one to follow, using whatever
         techniques the user prefers. (CUSTOM)"""

        prob = self._retrieve_check_paths(all_enabled_trans)
        self._check_type_paths(prob)
        if prob[0] == 'AUTO':
                next = random.choices(list(range(0, len(all_enabled_trans), 1)))[0]
        elif prob[0] == 'CUSTOM':
            self.call_custom_xor_function(all_enabled_trans)
        elif type(prob[0] == float()):
            if not self._check_probability(prob):
                value = [*range(0, len(prob), 1)]
                next = int(random.choices(value, prob)[0])
            else:
                next = random.choices(list(range(0, len(all_enabled_trans), 1)))[0]

        return all_enabled_trans[next]

    def _delete_tokens(self, name):
        to_delete = []
        for p in self._am:
            if p.name != name:
                to_delete.append(p)
        return to_delete

    def call_custom_xor_function(self, all_enabled_trans):
        """Define the custom method to determine the path to follow up (See example ...)."""
        print('Possible transitions of patrinet: ', all_enabled_trans)

    def next_transition(self, env):
        all_enabled_trans = semantics.enabled_transitions(self._net, self._am)
        all_enabled_trans = list(all_enabled_trans)
        all_enabled_trans.sort(key=lambda x: x.name)
        label_element = str(list(self._am)[0])
        if len(all_enabled_trans) == 0:
            return None
        elif len(self._am) == 1:  ### caso di un singolo token processato dentro petrinet
            if len(all_enabled_trans) > 1:
                return self.define_xor_next_activity(all_enabled_trans)
            else:
                return all_enabled_trans[0]
        else:
            events = []
            for token in self._am:
                name = token.name
                new_am = copy.copy(self._am)
                tokens_to_delete = self._delete_tokens(name)
                for p in tokens_to_delete:
                    del new_am[p]
                path = env.process(Token(self._id, self._net, new_am, self._params, self._process, self._prefix, "parallel", self._writer).simulation(env))
                events.append(path)

            return events