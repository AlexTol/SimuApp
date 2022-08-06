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
        self.containerAgent2 = DQNAgent(static_size + l3dynamic_size,1,logFile1)

    def getActualServer(dims):



    def act1(serverTaskDimList,static_size):
        maxActVal = 0
        maxChoice 0
        maxIndex = 0
        choices = []
        for i in  range(0,len(serverTaskDimList)):
            top_index,act_vals = act1.actSurrogate(serverTaskDimList)
            currentVal = act_vals[top_index]
            choices.append(top_index)
            if(currentVal > maxActVal):
                maxActVal = currentVal
                maxChoice = top_index
                maxIndex = i
        
        return choices,self.getActualServer(serverTaskDimList[maxIndex]),serverTaskDimList[maxIndex]
