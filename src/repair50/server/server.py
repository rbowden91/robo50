import sys
import os
import json
import selectors
import uuid
import socket
import selectors
import time

from collections import namedtuple
from queue import Queue as ThreadQueue
from threading import Lock as ThreadLock, Thread
from typing import Dict, Union
from multiprocessing import Process, Pipe, Lock, Queue

import numpy as np # type:ignore
import tensorflow as tf #type:ignore
import collections


#from ..utils import dprint
from ..default_dict import get_dict
from ..model.config import joint_configs, dependency_configs, valid_dependencies #type:ignore
from ..wrangler.wrangle import finish_row, wrangle, process_ast #type:ignore
from .c_generator import CGenerator

# info, warning, error, never_print
LOG_LEVEL = 0

def log_print(string, log_level=0):
    if log_level >= LOG_LEVEL:
        print(string)

def get_cells(self, node_id, prop, data_dict, initials_dict, test):
    for dconfig in prop:
        for cdependency in prop[dconfig]:
            # TODO: this has different labels/attrs for each dependency config
            for k in ['forward', 'reverse']:
                for j in ['attr', 'label']:
                    token = prop[dconfig][cdependency]['label_index']['expected_' + j]
                    index = self.config['lexicon'][test][j][token]
                    data_dict[self.config['features'][k + '-' + j + '_index']] = [[0, index]]

            config['session'].run(self.config['tensor_iter'], data_dict)
            vals = config['session'].run(self.config['fetches'], initials_dict)
            prop = self.gather_props(vals, data_dict, node_id=node_id)
            return prop

def beam_step(self, props, test=None):#, label, attr, transition, dependencies):
    config = self.config

    data_dict = {}
    initials_dict = {}
    for k in props['forward']:
        for dc in config['initials']['dependency_configs']:
            if k in config['initials']['dependency_configs'][dc]:
                dep_id = props['forward'][k]
                if dep_id == 0:
                    dep_label_idx = 0
                    dep_attr_idx = 0
                else:
                    dep_prop = self.data.prop_map[dep_id][test]
                    dep_label = dep_prop['dependency_configs'][dc]['label_index']['actual_label']
                    dep_attr = dep_prop['dependency_configs'][dc]['label_index']['actual_attr']
                    dep_label_idx = self.config['lexicon'][test]['label'][dep_label]
                    dep_attr_idx = self.config['lexicon'][test]['attr'][dep_attr]
                for q in config['initials']['dependency_configs'][dc][k]:
                    initials_dict[config['initials']['dependency_configs'][dc][k][q]] = \
                        [config['cells']['dependency_configs'][dc][k][q][dep_id][dep_label_idx][dep_attr_idx]]
        for direction in ['forward', 'reverse']:
            key = direction + '-' + k
            if key not in config['features']: continue
            if k in valid_dependencies.keys():
                data_dict[config['features'][key]] = [[0, 0]]
            else:
                data_dict[config['features'][key]] = [[0, props[direction][k]]]

    for direction in ['forward', 'reverse']:
        data_dict[config['features'][direction + '-mask']] = [[0, 1]]

    for k in config['features']:
        if config['features'][k] not in data_dict:
            data_dict[config['features'][k]] = [[0, 0]]
    config['session'].run(config['tensor_iter'], data_dict)
    # need to pass in inital cell values here
    vals = config['session'].run(config['fetches'], initials_dict)
    node_id = self.data.num_nodes
    self.data.num_nodes+=1
    prop = self.gather_props(vals, data_dict, node_id=node_id)
    prop = self.get_cells(node_id, prop, data_dict, initials_dict, test)
    return node_id, prop

def beam_row(self, parent_node_id, direction, test, dconfig, cdependency):
    row = []
    while True:
        props = { 'forward': {}, 'reverse': {} }
        props[direction]['parent'] = parent_node_id
        props[direction]['left_sibling' if direction == 'forward' else 'right_sibling'] = \
                row[-1] if len(row) > 0 else 0
        node_id, prop = self.beam_step(props)
        props.update(prop)
        if node_id not in self.data.prop_map:
            self.data.prop_map[node_id] = {}
        self.data.prop_map[node_id]['props'][test] = props
        row.append(node_id)
        if prop[dconfig][cdependency]['last_sibling' if direction == 'forward' else 'first_sibling']['expected'] > 0.5:
            break
    if direction == 'reverse':
        row.reverse()
    return row

def beam(self, dconfig, cdependency, node_id=39, test=None):
    direction = 'forward' if dconfig == 'joint_configs' or \
                dependency_configs[cdependency][-1][0] else 'reverse'

    queue = [node_id]
    while len(queue) > 0:
        node_id = queue.pop(0)
        row = self.beam_row(node_id, direction, test, dconfig, cdependency)
        # TODO: learn these from the data
        # ExpressionList? Have an attr that is if it is empty or not
        for node_id in row:
            prop = self.data.prop_map[node_id]['props'][test][dconfig][cdependency]
            if prop['label_index']['actual_label'] not in ['Constant', 'IdentifierType', 'ID', 'ExpressionList', 'Exprlist']:
                queue.append(node_id)






#import check_correct
#import queue as Q
#max_changes = 3
# side effect: populate node_properties with parent pointers (not yet used?)
#def fill_queue(node, node_properties, q, parent=None):
#    node_properties[node]['parent'] = parent
#
#    score = node_properties[node]['attr_ratio']
#    # XXX for now, time.time() is supposed to make sure that we never get to comparing nodes
#    q.put((score, time.time(), node))
#    children = node.children()
#    for i in range(len(children)):
#        fill_queue(children[i][1], node_properties, q, node)
#
## XXX heuristics about class name?
#def search_changes(ast, node_properties, list_q, max_changes, filename, directives, start = 0, num_changes = 0):
#    for i in range(start, len(list_q)):
#        node = list_q[i][2]
#        # adjust this cutoff?
#        if node_properties[node]['attr_ratio'] == 1.0:
#            break
#        nvlist = [(n, getattr(node, n)) for n in node.attr_names]
#        for (name, val) in nvlist:
#            if name in ['value', 'op', 'name']:
#                setattr(node, name, node_properties[node]['attr_expected'])
#                if num_changes == max_changes - 1:
#                    #try:
#                        #code = directives + generator.visit(ast)
#                        path = os.path.join(FLAGS.task_path, '.' + filename + '.c')
#                        with open(path, 'w') as f:
#                            f.write(code)
#                        ret = check_correct.check_vigenere(path)
#                        os.unlink(path)
#                        if ret == 0:
#                            return code
#                    #except Exception:
#                    #    #print('uh ohhh')
#                    #    pass
#                else:
#                    ret = search_changes(ast, node_properties, list_q, max_changes, filename, directives, start=i+1, num_changes=num_changes+1)
#                    # Success! The ast is now repaired
#                    if ret is not False:
#                        return ret
#                # no luck, revert to the old value
#                setattr(node, name, val)
#                break
#    # didn't find a working tree
#    return False
#
#
#
#def search(ast, node_properties, filename, directives):
#    # XXX check if code already works?
#    #code = generator.visit(ast)
#    #path = os.path.join(FLAGS.task_path, '.' + filename + '.c')
#    #with open(path, 'w') as f:
#    #    f.write(code)
#    #ret = check_correct.check_vigenere(path)
#    #os.unlink(path)
#    #if ret == 0:
#    #    return code
#    q = Q.PriorityQueue()
#    fill_queue(ast, node_properties, q)
#    list_q = []
#    while not q.empty():
#        list_q.append(q.get())
#    for i in range(max_changes):
#        code = search_changes(ast, node_properties, list_q, i+1, filename, directives)
#        if code is not False:
#            return code
#    return False

# base class

class ServerProcess(object):
    def __init__(self, input_queue, origin_pipe) -> None:
        self.input_queue = input_queue
        self.origin_pipe = origin_pipe
        self.loop()

    def loop(self):
        while True:
            handler, *args = self.input_queue.get()
            if handler == 'load_config':
                self.load_config(*args)
            elif handler == 'handle_input':
                output = self.handle_input(*args)
                if output is not False:
                    socket, socket_data, *args = args
                    self.origin_pipe.send((socket, socket_data, *output))
            else:
                assert False

class ServerModelProcess(ServerProcess):
    def __init__(self, *args, **kwargs) -> None:
        self.test_config = {} #type:ignore
        super().__init__(*args, **kwargs)

    def load_config(self, model_path, save_path):
        with open(os.path.join(model_path, 'config.json'), 'r') as f:
            test_conf = json.load(f)
        d = get_dict(self.test_config, test_conf['test'], test_conf['root_transitions_idx'])
        d[test_conf['transitions']] = test_conf
        with open(os.path.join(model_path, save_path, 'config.json'), 'r') as f:
            test_conf.update(json.load(f))

        test_conf['graph'] = tf.Graph()
        # fix windows line endings
        test_conf['best_dir'] = test_conf['best_dir'].replace('\\', '/')
        with test_conf['graph'].as_default():
            saver = tf.train.import_meta_graph(os.path.join(test_conf['best_dir'], "model.meta"))
            test_conf['session'] = tf.Session(config=tf.ConfigProto(device_count = {'GPU': 0}))
            saver.restore(test_conf['session'], os.path.join(test_conf['best_dir'], 'model'))
        log_print('Loaded model {} {} {}'.format(test_conf['test'], test_conf['root_idx'], test_conf['transitions']), 1)

    def handle_input(self, socket, socket_data, opaque, code, rows, test,
                     root_node_idx, root_trans_idx, transitions):
        test_conf = self.test_config[test][root_trans_idx][transitions]

        log_print('Running model {} {} {}'.format(test, root_trans_idx, transitions), 0)
        lexicon = test_conf['lexicon']
        node_nums = rows['forward-node_num']
        row = finish_row(rows, lexicon['token_to_index'])
        data_dict = {}
        for k in test_conf['features']:
            data_dict[test_conf['features'][k]] = [row[k]]

        with test_conf['graph'].as_default():
            test_conf['session'].run(test_conf['tensor_iter'], data_dict)

            vals = test_conf['session'].run(test_conf['fetches'])
        props = {}
        codeProps = {}
        dependencyConfigs = {cdependency: True for cdependency in vals['dependency_configs']}
        for i in range(1, len(row['forward-self'])):
            idx = {'forward': row['forward-self'][i], 'reverse': row['reverse-self'][i]}
            props[idx['forward']] = prop = self.gather_props(self.test_config[test][root_trans_idx][transitions], vals, data_dict, idx)
            codeProps[node_nums[i-1]] = {'test_data': { test: { 'model_results': { root_node_idx: { transitions: prop } } } } };
        output = { 'codeProps': codeProps, 'dependencyConfigOptions': dependencyConfigs }
        if opaque is not None:
            output['opaque'] = opaque
        return [output]

    #for test in self.test_conf:
    #    for root_idx in rows[test]:
    #        if test == 'null' or len(rows[test][root_idx][True]) == 0: continue

    #        root_node = data.prop_map[root_idx]['props']
    #        root_props = root_node[test][root_idx][True]
    #        if not root_props['unknown_transitions']: continue
    #        root_props['suggested_trans_groups'] = collections.defaultdict(int)
    #        for test2 in data.nodes:
    #            if test2 == 'null' or test == test2: continue
    #            root_props2 = root_node[test2][root_idx][True]
    #            if not root_props2 or 'root_trans_idx' not in root_props2: continue
    #            tg = self.test_conf[test2][root_props2['root_trans_idx']][True]
    #            #if not tg: continue
    #            tg = tg['transitions_groups'][test]
    #            for correct_transitions in tg:
    #                root_props['suggested_trans_groups'][correct_transitions] += tg[correct_transitions]


    def gather_props(self, test_config, vals, data_dict, diridx):
        tc = test_config
        revlex = tc['lexicon']['index_to_token']
        lex = tc['lexicon']['token_to_index']
        transitions = tc['transitions'] == 'true'
        features = tc['features']

        prop = {dconfig : {cdependency: {} for cdependency in vals[dconfig]} for dconfig in vals}
        for dconfig in vals:
            for cdependency in vals[dconfig]:
                v = vals[dconfig][cdependency]
                direction = 'forward' if dconfig == 'joint_configs' or \
                            dependency_configs[cdependency][-1][0] else 'reverse'
                prop[dconfig][cdependency]['direction'] = direction
                idx = diridx[direction]

                if transitions:
                    token_target = data_dict[features[direction + '-transitions_index']][0][idx]
                else:
                    token_target = data_dict[features[direction + '-label_index']][0][idx]
                    attr_target = data_dict[features[direction + '-attr_index']][0][idx]

                #for dependency in v['cells']:
                #    for k in v['cells'][dependency]:
                #        if node_id not in config['cells'][dconfig][cdependency][dependency][k]:
                #            config['cells'][dconfig][cdependency][dependency][k][node_id] = {}
                #        cells = config['cells'][dconfig][cdependency][dependency][k][node_id]
                #        if transitions:
                #            cells[token_target] = v['cells'][dependency][k][0][idx].tolist()
                #        else:
                #            if token_target not in cells:
                #                cells[token_target] = {}
                #            cells[token_target][attr_target] = v['cells'][dependency][k][0][idx].tolist()

                for k in vals[dconfig][cdependency]['loss']:
                    # attr_index handled within label_index
                    if k == 'attr_index': continue

                    prop[dconfig][cdependency][k] = p = {}

                    probs = v['probabilities'][k][0]
                    if dconfig == 'joint_configs':
                        p['alpha'] = alpha = probs[idx].tolist()
                        sum_probs = 0
                        for jd in range(len(joint_configs[cdependency])):
                            joint_dependency = joint_configs[cdependency][jd]
                            probs = vals['dependency_configs'][joint_dependency][k]['probabilities'][0][idx]
                            sum_probs += alpha[jd] * probs
                        probs = sum_probs
                    else:
                        probs = probs[idx]

                    if k == 'label_index' or k == 'transitions_index':

                        p['actual_probability'] = float(probs[token_target])
                        if not transitions:
                            p['actual_probability'] *= float(v['probabilities']['attr_index'][0][idx][attr_target])

                        if k == 'label_index':
                            new_probs = []
                            for token_idx in range(len(probs)):
                                token = (float(probs[token_idx]), revlex['label'][str(token_idx)])

                                attr_probs = v['attr_all'][0][idx][token_idx]
                                new_probs.extend([(token[0] * float(attr_probs[j]),
                                                    token[1], revlex['attr'][str(j)]) for j in range(len(attr_probs))])
                            probs = new_probs
                            p['actual_attr'] = revlex['attr'][str(attr_target)]
                            p['actual_label'] = revlex['label'][str(token_target)]
                        else:
                            probs = [(float(probs[j]), revlex['transitions'][str(j)]) for j in range(len(probs))]
                            #probs = probs.tolist()
                            p['actual_transitions'] = revlex['transitions'][str(token_target)]

                        probs.sort(key=lambda x: x[0], reverse=True)
                        p['probabilities'] = [x for x in probs if x[0] > .001]
                        expected_probability = float(probs[0][0])
                        p['ratio'] = p['actual_probability'] / expected_probability
                    elif k == 'pointers':
                        p['actual'] = []
                        for q in range(20):
                            target = data_dict[features[direction + '-pointers-mask-' + str(q)]][0][idx]
                            p['actual'].append(target)
                        p['expected'] = probs.tolist()
                    else:
                        target = data_dict[features[direction + '-' + k]][0][idx]
                        p['actual'] = target
                        p['expected'] = probs.tolist()

        return prop

class ServerTestProcess(ServerProcess):
    def __init__(self, model_processes, c_generator, *args, **kwargs):
        self.test_config = {}
        self.unit_tests = {}
        self.model_processes = model_processes
        self.model_process_map = {}
        self.c_generator = c_generator
        super().__init__(*args, **kwargs)

    def load_config(self, test, path, save_path):
        with open(os.path.join(path, 'config.json'), 'r') as f:
            self.test_config[test] = json.load(f)
        if test != 'null':
            self.unit_tests[test] = self.test_config[test]['unit_test']

        total_models = 0
        for root_idx in os.listdir(path):
            if root_idx == 'config.json': continue
            for transitions in os.listdir(os.path.join(path, root_idx)):
                model_path = os.path.join(path, root_idx, transitions)
                p = self.model_processes[total_models % len(self.model_processes)]
                total_models += 1
                p['queue'].put(('load_config', model_path, save_path))
                get_dict(self.model_process_map, test, root_idx)[transitions] = p

        log_print('Test {} initialized'.format(test), 1)

    def handle_input(self, socket, socket_data, opaque, code):
        try:
            ast_data = wrangle(code, tests=self.unit_tests, is_file=False)
        except Exception as e:
            return {'error': "Couldn't parse code." + str(e)}

        rows = process_ast(ast_data)

        send_data = 0
        for test in self.model_process_map:
            root_lex = self.test_config[test]['root_lex']['transitions']
            mpm = self.model_process_map[test]
            for root_node_idx in rows[test]:
                for transitions in rows[test][root_node_idx]:
                    root_node = ast_data.prop_map[root_node_idx]
                    root_test_data = ast_data.prop_map[root_node_idx]['test_data'][test]
                    root_transitions = root_test_data['transitions']
                    if root_transitions == '<unk>' or root_transitions not in root_lex:
                        root_test_data['unknown_transitions'] = True
                        continue
                    root_trans_idx = str(root_lex[root_transitions])
                    root_test_data['unknown_transitions'] = False
                    root_test_data['root_trans_idx'] = root_trans_idx
                    if root_trans_idx not in mpm or \
                            transitions not in mpm[root_trans_idx]:
                        # XXX this one isn't quite "unknown". We just didn't have enough test data???
                        root_test_data['unknown_transitions'] = True
                        continue
                    mpm[root_trans_idx][transitions]['queue'].put((
                        'handle_input',
                        socket,
                        socket_data,
                        opaque,
                        code,
                        rows[test][root_node_idx][transitions],
                        test,
                        root_node_idx,
                        root_trans_idx,
                        transitions,
                        ))
                    send_data += 1

        #output['total_model_data'] = send_data
        #codeProps = {}
        #print(ast_data.prop_map)
        #for node_num in ast_data.prop_map:
            #node = ast_data.prop_map[node_num]
            #codeProps[node_num]
            #if 'props' in codeProps[node_num]:
            #for k in ['pointers', 'replace_name', 'props']:
            #    if k in codeProps[node_num]:
            #        del(codeProps[node_num][k])
        output = { 'codeProps': ast_data.prop_map, 'testResults': ast_data.results }
        if self.c_generator:
            output['code'] = CGenerator(ast_data).code
        if opaque is not None:
            output['opaque'] = opaque
        return [output]


class ServerSocketProcess(ServerProcess):
    def __init__(self, test_processes, *args, **kwargs):
        self.test_processes = test_processes
        super().__init__(*args, **kwargs)

    # SENDING RESPONSE METHODS

    def send_msg(self, socket,  msg):
        assert isinstance(msg, dict)
        msg = json.dumps(msg).encode('latin-1') + b'\n\n'
        sleep_error = 0
        # TODO: instead, put it to sleep (using EVENT_WRITE)?
        while len(msg) > 0 and sleep_error <= 10:
            try:
                sent = socket.send(msg)
                msg = msg[sent:]
                sleep_error = 0
            except:
                sleep_error += 1
                time.sleep(1)
        return len(msg) == 0

    # HANDLING INPUT METHODS
    # accepting input from the origin server (must take self, data, and mask)

    def handle_input(self, fileobj, fileobj_data, mask):
        if fileobj_data['type'] in [ServerTestProcess, ServerModelProcess]:
            return self.handle_server_pipe(fileobj, fileobj_data, mask)
        elif fileobj_data['type'] == 'client_socket':
            return self.handle_client_socket(fileobj, fileobj_data, mask)
        else:
            assert False

        method = getattr(self, handler)
        return method(*args)

    def handle_server_pipe(self, server_pipe, server_pipe_data, mask):
        try:
            socket, socket_data, output = server_pipe.recv()
        except:
            assert False
            # TODO: "socket" is never re-registered?
            return ['close_server_pipe']
        self.origin_pipe.send((server_pipe, server_pipe_data, 'register_server_pipe'))
        if self.send_msg(socket, output):
            self.origin_pipe.send((socket, socket_data, 'register_client_socket'))
        else:
            self.origin_pipe.send((socket, socket_data, 'close_client_socket'))

        return False

    def handle_client_socket(self, socket, socket_data, mask):
        log_print('Handling input')
        if mask & selectors.EVENT_READ:
            while True:
                try:
                    recv_data = socket.recv(4096)
                    if not recv_data:
                        # client socket closed connection itself
                        return ['close_client_socket']
                    # TODO reject if this gets too big
                    socket_data['input'] += recv_data
                except:
                    # this is fine, it just meant we would have blocked
                    break
            try:
                socket_data['input'].index(b'\n\n')
            except ValueError:
                return ['register_client_socket']

            input_ = socket_data['input'].split(b'\n\n')
            socket_data['input'] = input_.pop()
            for i in range(len(input_)):
                try:
                    input_[i] = json.loads(input_[i])
                except:
                    if not self.send_msg(socket, {'output': { 'error': 'Unable to parse input json'}}):
                        return ['close_client_socket']
            self.origin_pipe.send((socket, socket_data, 'register_client_socket'))

            for i in range(len(input_)):
                if 'opaque' not in input_[i]:
                    input_[i]['opaque'] = None
                for tp in self.test_processes:
                    tp['queue'].put(('handle_input', socket, socket_data, input_[i]['opaque'], input_[i]['code']))

            return False

        #elif mask & selectors.EVENT_WRITE:
            #pass
            #self.send_msg(data
            #send_


class Server(object):
    def __init__(self, args):
        self.sel = selectors.DefaultSelector()

        self.model_processes = self.spawn_processes(ServerModelProcess, False, False, args.num_model_processes)

        total_tests = 0
        self.test_processes = []
        for test in os.listdir(args.data_path):
            if args.subtests is None or test not in args.subtests: continue
            if args.num_test_processes is None or len(self.test_processes) < args.num_test_processes:
                self.test_processes.extend(self.spawn_processes(ServerTestProcess, False, False, 1, self.model_processes, total_tests == 0))
            tp = self.test_processes[total_tests % len(self.test_processes)]
            tp['queue'].put(('load_config', test, os.path.join(args.data_path, test), args.save_path))
            total_tests += 1

        self.socket_processes = self.spawn_processes(ServerSocketProcess, True, True, args.num_socket_processes, self.test_processes)

        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind((args.host, args.port))
        lsock.setblocking(False)
        lsock.listen()

        self.sel.register(lsock, selectors.EVENT_READ, data={'type': 'incoming_connections'})
        log_print('listening on {}:{}'.format(args.host, args.port), 1)

        self.loop()

# TODO: disconnect after timeout, messages too long, etc.
# TODO: kill subprocesses?
    def loop(self):
        while True:
            events = self.sel.select(timeout=None)
            for key, mask in events:
                data = key.data
                if data['type'] == 'incoming_connections':
                    conn, addr = key.fileobj.accept()
                    self.sel.register(conn, selectors.EVENT_READ, data={'type': 'client_socket', 'input':b'', 'output':b''})
                    conn.setblocking(False)
                    log_print('accepted connection from {}'.format(addr))
                elif data['type'] in [ServerTestProcess, ServerModelProcess, 'client_socket']:
                    self.sel.unregister(key.fileobj)
                    # send the output off to a server socket
                    self.socket_processes[0]['queue'].put(('handle_input', key.fileobj, data, mask))
                elif data['type'] == ServerSocketProcess:
                    # TODO: do we have to worry about this recv at all? slow or failing?
                    # we don't about the ServerSocketProcess's socket / socket_data that came back
                    socket, socket_data, output = key.fileobj.recv()
                    if output in ['register_client_socket', 'register_server_pipe']:
                        self.sel.register(socket, selectors.EVENT_READ, data=socket_data)
                    elif output in ['close_server_socket', 'close_server_pipe']:
                        socket.close()
                else:
                    print(data['type'])
                    assert False


    def shutdown(self):
        # TODO: this doesn't handle sockets that are currently floating around in subprocesses
        for socket in self.sel.get_map():
            self.sel.unregister(socket)
            socket.close()
        self.sel.close()

    def spawn_processes(self, process_type, is_thread, share_queue, num_processes, *args):
        # also, is there a ThreadPipe of some kind?
        input_q = None
        processes = []
        for i in range(num_processes):
            # TODO: should this pipe be closed???
            parent_pipe, child_pipe = Pipe(False)
            self.sel.register(parent_pipe, selectors.EVENT_READ, data={'type': process_type})
            if is_thread:
                spawn = Thread
                new_q = ThreadQueue #type:ignore
            else:
                spawn = Process
                new_q = Queue
            if input_q is None or not share_queue:
                input_q = new_q()
            p = spawn(target=process_type, args=(*args, input_q, child_pipe))
            p.daemon = True
            p.start()
            processes.append({'process': p, 'queue': input_q, 'pipe': parent_pipe})
        return processes
