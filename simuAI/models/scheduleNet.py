import random
import torch as T
import torch.nn as nn
import torch.nn.functional as F 
import torch.optim as optim
import numpy as np
from collections import deque 
from models.dqn import DQNAgent
import os

class ScheduleNet(nn.Module):
    def __init__(self,static_size,l1dynamic_size,l2dynamic_size,l3dynamic_size,logFile1=False,logFile2=False,logFile3=False):
        super(ScheduleNet, self).__init__()
        self.static_size = static_size
        self.servAgent = DQNAgent(static_size + l1dynamic_size,2,logFile1)
        self.containerAgent1 = DQNAgent(static_size + l2dynamic_size,2,logFile2)
        self.containerAgent2 = DQNAgent(static_size + l3dynamic_size,2,logFile3)


    def act1(self,serverTaskDimList,servers):
        maxActVal = 0
        maxIndex = 0
        choices = []
        for i in  range(0,len(serverTaskDimList)):
            top_index,act_vals = self.servAgent.actSurrogate(serverTaskDimList[i])
            currentVal = act_vals[top_index]
            choices.append(top_index)
            if(currentVal > maxActVal):
                maxActVal = currentVal
                maxIndex = i
        
        return choices,servers[maxIndex]

    def act2(self,containerTaskDimList,conObjs,conNames):
        choices = []
        chosenCons = []
        chosenConObjs = []
        chosenConNames = []
        for i in range(0,len(containerTaskDimList)):
            top_index,act_vals = self.containerAgent1.actSurrogate(containerTaskDimList[i])
            choices.append(top_index)
            if(act_vals[top_index] == 1):
                chosenCons.append(containerTaskDimList[i])
                chosenConObjs.append(conObjs[i])
                chosenConNames.append(conNames[i])
        
        if(len(chosenCons) == 0):
            chosenCons.append(containerTaskDimList[0])
            chosenConObjs.append(conObjs[0])
            chosenConNames.append(conNames[0])

        print("ACT2 choices")
        print(choices)
        return choices,chosenCons,chosenConObjs,chosenConNames

    def act3(self,chosencontainerTaskDimList):
        maxActVal = 0
        maxIndex = 0
        choices = []
        for i in range(0,len(chosencontainerTaskDimList)):
            top_index,act_vals = self.containerAgent2.actSurrogate(chosencontainerTaskDimList[i])
            currentVal = act_vals[top_index]
            choices.append(top_index)
            if(currentVal > maxActVal):
                maxActVal = currentVal
                maxIndex = i

        #print(chosencontainerTaskDimList[maxIndex])
        return choices,chosencontainerTaskDimList[maxIndex][12]

    def remember(self,layer,states,actions,rewards,next_states):
        #print("states len")
        #print(len(states))
        #print("actions len")
        #print(len(actions))
        #print("rewards len")
        #print(len(rewards))
        #print("next_states len")
        #print(len(next_states))
        if(layer == 1):
            for i in range(0,len(states)):
                self.servAgent.remember(states[i],actions[i],rewards[i],next_states[i],False)
        elif(layer == 2):
            for i in range(0,len(states)):
                self.containerAgent1.remember(states[i],actions[i],rewards[i],next_states[i],False)
        else:
            for i in range(0,len(states)):
                self.containerAgent2.remember(states[i],actions[i],rewards[i],next_states[i],False)

    def replay(self,batch_size):
        self.servAgent.replay(batch_size)
        self.containerAgent1.replay(batch_size)
        self.containerAgent2.replay(batch_size)