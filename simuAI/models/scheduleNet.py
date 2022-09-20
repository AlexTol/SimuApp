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
    def __init__(self,l1dynamic_size,l2dynamic_size,l3dynamic_size,logFile1=False,logFile2=False,logFile3=False):
        super(ScheduleNet, self).__init__()
        #self.static_size = static_size
        self.servAgent = DQNAgent(l1dynamic_size,2,logFile1)
        self.containerAgent1 = DQNAgent(l2dynamic_size,2,logFile2)
        self.containerAgent2 = DQNAgent(l3dynamic_size,2,logFile3)


    def act1(self,serverTaskDimList,servers):
        maxActVal = 0
        maxIndex = 0
        choices = []
        for i in  range(0,len(serverTaskDimList)):
            top_index,act_vals = self.servAgent.actSurrogate(serverTaskDimList[i])
            if(top_index == -1):#need to do this due to pytorch >=.5 quirk
                top_index = act_vals # this may be incorrect since it doesn't return a confidence value, I might want to change this up
                if(maxActVal == 0):
                    currentVal = (random.randrange(2))
                else:
                    currentVal = (random.randrange(2)) * maxActVal
            else:
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
            
            if(top_index == -1):#need to do this due to pytorch >=.5 quirk
                choice = act_vals 
            else:
                choice = top_index
            choices.append(choice)
            #print("DIMLIST : " + str(containerTaskDimList[i]) + " ,conName: " + str(conNames[i]) + " ,CONOBJ: " + str(conObjs[i]) + " ,CHOICE : " + str(choice) + "\n")
            #print("CHOICE : " + str(choice) + "\n")
            if(choice == 1):
                chosenCons.append(containerTaskDimList[i])
                chosenConObjs.append(conObjs[i])
                chosenConNames.append(conNames[i])
        
        if(len(chosenCons) == 0):
            chosenCons.append(containerTaskDimList[0])
            chosenConObjs.append(conObjs[0])
            chosenConNames.append(conNames[0])

        #print("ACT2 choices")
        #print(choices)
        return choices,chosenCons,chosenConObjs,chosenConNames

    def act3(self,chosencontainerTaskDimList,chosenConNames):
        maxActVal = 0
        maxIndex = 0
        choices = []
        for i in range(0,len(chosencontainerTaskDimList)):
            top_index,act_vals = self.containerAgent2.actSurrogate(chosencontainerTaskDimList[i])
            if(top_index == -1):#need to do this due to pytorch >=.5 quirk
                currentVal = act_vals
            else:
                currentVal = act_vals[top_index]
            choices.append(top_index)
            if(currentVal > maxActVal):
                maxActVal = currentVal
                maxIndex = i

        #print(chosencontainerTaskDimList[maxIndex])
        return choices,chosenConNames[maxIndex]

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
                #print("state: " + str(states[i]) + " ,action: " + str(actions[i]) + " ,reward: " + str(rewards[i]) + " ,next_state: " + str(next_states[i]))
                self.containerAgent1.remember(states[i],actions[i],rewards[i],next_states[i],False)
        else:
            for i in range(0,len(states)):
                #print("state: " + str(states[i]) + " ,action: " + str(actions[i]) + " ,reward: " + str(rewards[i]) + " ,next_state: " + str(next_states[i]))
                self.containerAgent2.remember(states[i],actions[i],rewards[i],next_states[i],False)

    def replay(self,batch_size):
        self.servAgent.replay(10,True)
        self.containerAgent1.replay(10,True)
        self.containerAgent2.replay(10)