import sys

from myconfig import *
import pickle
import json
import numpy as np
from action_proposal_util import Vehicle, output_activity
from collections import defaultdict

import torch
import torch.nn as nn
from torch.autograd import Variable
from model import Bid_RNN

"""
detection region proposal by 1-d score array
given a score array
s*,e* = argmax_{s,e} \sum_{t=s}^{e} (score[t]-\lambda)
    scores: score array
    ld: lambda
"""
def detect_from_score_array(scores, ld):
    scores = scores-ld
    s,e,cur_sum = 0,0,scores[0]
    s_mx, e_mx, sum_mx = -1,-1,0
    for i in range(1, len(scores)):
        e+=1
        cur_sum += scores[i]
        if cur_sum>sum_mx:
            s_mx, e_mx, sum_mx = s,e,cur_sum
        if cur_sum<=0 and i<len(scores)-1: 
            s,e,cur_sum = i+1, i, 0
    return s_mx,e_mx,sum_mx


"""
for each tracklet, store it as a list of (timestamp, bbox)
"""
def read_mot_as_defaultdict(mot_output_fn):
    trackdict = defaultdict(list)
    for l in open(mot_output_fn):
        lst = [int(i) for i in l.split(',')]
        t = lst[0]-1
        box = lst[2:6]
        trackdict[lst[1]].append((t,box))
    return trackdict

def topk_avg_score(scores, k=8):
    scores = sorted(scores, reverse=True)
    if len(scores)<k: return np.mean(scores)
    else: return np.mean(scores[:k])


model = Bid_RNN(4, 4, class_num=4).cuda()
# model = Bid_RNN(2, 4, class_num=4).cuda()
# model = One_RNN(2, 16, class_num=4).cuda()
model.eval()
model.load_state_dict(torch.load('rnn_state_all_epoch_10.pt'))
softmax = nn.Softmax().cuda()

scene_2_valid = ['VIRAT_S_040103_00_000000_000120', 'VIRAT_S_040103_01_000132_000195', 'VIRAT_S_040103_02_000199_000279', 
                  'VIRAT_S_040103_03_000284_000425', 'VIRAT_S_040103_06_000836_000909', 'VIRAT_S_040104_07_001268_001348']

scene_2_train = ['VIRAT_S_040103_05_000729_000804', 'VIRAT_S_040103_07_001011_001093', 'VIRAT_S_040103_08_001475_001512', 
                'VIRAT_S_040104_00_000120_000224','VIRAT_S_040104_01_000227_000457', 'VIRAT_S_040104_02_000459_000721', 
                'VIRAT_S_040104_04_000854_000934','VIRAT_S_040104_05_000939_001116','VIRAT_S_040104_06_001121_001241',
                'VIRAT_S_040104_09_001475_001583']

scene_1_valid = ['VIRAT_S_000007', 'VIRAT_S_000008']

scene_1_train = ['VIRAT_S_000000','VIRAT_S_000001','VIRAT_S_000002','VIRAT_S_000005']


### NIST evaluation output
sys_out = {}                                                                                                                                                                                                        
sys_out['activities'] = []                                                                                                                                                                                          
actcount = 0
step = 150
ld = 0.05
# for vid in scene_2_valid + scene_1_valid:
for vid in valid_vid_list:
    try:
        trackdict = read_mot_as_defaultdict(car_trk_dir+vid+'.txt')
    except:
        print("Not present anywhere!")
    # trackdict = read_mot_as_defaultdict(car_trk_dir+vid+'.txt')
    
    feats, labs = pickle.load(open('data/'+vid+'.pkl','rb'))
    keys = []
    for k, feat, lab in zip(trackdict.keys(), feats, labs):
        start = min([t for t, box in trackdict[k]])
        end = max([t for t, box in trackdict[k]])
        if end-start<10: continue
        car = Vehicle(k, trackdict[k])
        vmean = np.mean([np.linalg.norm(car.vs[i,:]) for i in range(len(car.vs))])
        if vmean<1.0: continue
        else:
            keys.append(k)
    
    #for k in trackdict.keys():
    for k, feat, lab in zip(keys, feats, labs):

        ### preprocessing + simple pruning
        ### get rid of short tracklet and static tracklet
        start = min([t for t, box in trackdict[k]])
        end = max([t for t, box in trackdict[k]])
        if end-start<10: continue
        car = Vehicle(k, trackdict[k])
        vmean = np.mean([np.linalg.norm(car.vs[i,:]) for i in range(len(car.vs))])
        if vmean<1.0: continue

        for t in range(0,len(car.vs),step):
            ss, ee = t, min(len(car.vs), t+2*step)
            if ee-ss<20: continue
            ### RNN frame-level detection
            #feat = Variable(torch.from_numpy(car.vs).cuda())
            feat_seg = Variable(torch.from_numpy(feat[ss:ee]).float().cuda())
            feat_seg = feat_seg.unsqueeze(0)
            out = model(feat_seg)
            out = softmax(out).data.cpu().numpy()


            ### turn right
            ## segment detection from RNN score
            scores = out[:,1]
            s,e,score = detect_from_score_array(scores, ld)
            print(s,e,score)
            ## output NIST format
            if s>0 and e>0 and e-s>5:
                #act_out = output_activity(actcount, name='vehicle_turning_right', score=score/(e-s+1), vid=vid, start=start+s, end=start+e)
                act_out = output_activity(actcount, name='vehicle_turning_right', score=topk_avg_score(scores[s:e+1].tolist()), vid=vid, start=start+ss+s, end=start+ss+e)
                sys_out['activities'].append(act_out)
                actcount+=1

            ### turn left
            ## segment detection from RNN score
            scores = out[:,2]
            s,e,score = detect_from_score_array(scores, ld)
            print(s,e,score)
            ## output NIST format
            if s>0 and e>0 and e-s>5:
                #act_out = output_activity(actcount, name='vehicle_turning_left', score=score/(e-s+1), vid=vid, start=start+s, end=start+e)
                act_out = output_activity(actcount, name='vehicle_turning_left', score=topk_avg_score(scores[s:e+1].tolist()), vid=vid, start=start+ss+s, end=start+ss+e)
                sys_out['activities'].append(act_out)
                actcount+=1

            scores = out[:,3]
            s,e,score = detect_from_score_array(scores, ld)
            print(s,e,score)
            ## output NIST format
            if s>0 and e>0 and e-s>5:
                #act_out = output_activity(actcount, name='vehicle_u_turn', score=score/(e-s+1), vid=vid, start=start+ss+s, end=start+ss+e)
                act_out = output_activity(actcount, name='vehicle_u_turn', score=topk_avg_score(scores[s:e+1].tolist()), vid=vid, start=start+ss+s, end=start+ss+e)
                sys_out['activities'].append(act_out)

                bbox = [car.get_box_from_t(start+tt) for tt in range(s,e+1)]
                actcount+=1



### output NIST format
# sys_out['filesProcessed'] = [vid+'.mp4' for vid in (scene_2_valid + scene_1_valid)]
sys_out['filesProcessed'] = [vid+'.mp4' for vid in valid_vid_list]
f = open('test/validation_sysout.json','w')
f.write(json.dumps(sys_out, indent=4)+'\n')
f.close()