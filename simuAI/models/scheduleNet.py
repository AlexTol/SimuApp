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
        self.static_size = state_size
        self.servAgent = DQNAgent(static_size + l1dynamic_size,2,logFile1)
        self.containerAgent1 = DQNAgent(static_size + l2dynamic_size,2,logFile1)
        self.containerAgent2 = DQNAgent(static_size + l3dynamic_size,2,logFile1)

    def getActualServer(dims): #returns the server number
        return dims[self.static_size] #server number will come right after the 

    def getActualContainer(dims): #returns the server number
        return dims[self.static_size] #server number will come right after the 

    def act1(self,serverTaskDimList):
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
        
        return choices,self.getActualServer(serverTaskDimList[maxIndex]),serverTaskDimList

    def act2(self,containerTaskDimList):
        choices = []
        chosenCons = []
        for i in range(0,len(containerTaskDimList)):
            top_index,act_vals = self.servAgent.actSurrogate(containerTaskDimList[i])
            choices.append(top_index)
            if(top_index == 1):
                chosenCons.append()
        
        return choices,containerTaskDimList,chosenCons

    def act3(self,chosencontainerTaskDimList):
        maxActVal = 0
        maxIndex = 0
        choices = []
        for i in range(0,len(chosencontainerTaskDimList)):
            top_index,act_vals = self.servAgent.actSurrogate(chosencontainerTaskDimList[i])
            currentVal = act_vals[top_index]
            choices.append(top_index)
            if(currentVal > maxActVal):
                maxActVal = currentVal
                maxIndex = i

        return choices,self.getActualContainer(chosencontainerTaskDimList[maxIndex]),chosencontainerTaskDimList

    def remember(self,states,actions,rewards,next_state):
        if(layer == 1):
            for i in range(0,len(states)):
                self.servAgent.remember((states[i],actions[i],rewards[i],next_state,False))
        elif(layer == 2):
            for i in range(0,len(states)):
                self.containerAgent1.remember((states[i],actions[i],rewards[i],next_state,False))
        else:
            for i in range(0,len(states)):
                self.containerAgent2.remember((states[i],actions[i],rewards[i],next_state,False))

    def replay(self,batch_size):
        self.servAgent.replay(batch_size)
        self.containerAgent1.replay(batch_size)
        self.containerAgent2.replay(batch_size)