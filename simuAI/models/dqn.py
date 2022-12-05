import random
import torch as T
import torch.nn as nn
import torch.nn.functional as F 
import torch.optim as optim
import numpy as np
from collections import deque 
import os

#define agent Credit for basic format to LiveLessons : https://www.youtube.com/watch?v=OYhFoMySoVs&t=3170s
class DQNAgent(nn.Module):
    def __init__(self,state_size,action_size,logFile=False,saveAgent="0",loadAgent="0",agentName="none"):
        super(DQNAgent, self).__init__()
        self.state_size = state_size
        self.action_size = action_size

        self.memory = deque(maxlen=2000) #remember previous decisions

        self.gamma = 0.95 #discount factor how much to discount future reward, near future is easier to guess than distant future

        self.epsilon = 1.0 # exploration rate for agent. The agent will look for new decisions and not rely on old proven decisions.
        self.epsilon_decay = 0.9 #even though we want the agent to explore, we still want it to rely on proven methods over time, original .995, winning is .9
        self.epsilon_min = 0.01 # even as epsilon decays, we still want it to explore from time to time

        self.learning_rate = 0.001 # step size of stochastic grad descent, original 0.001

        self.layer1 = nn.Linear(self.state_size, 256)
        self.layer1.weight.data.fill_(0)
        self.layer2 = nn.Linear(256, 256)
        self.layer2.weight.data.fill_(0)
        self.layer3 = nn.Linear(256, self.action_size)
        self.layer3.weight.data.fill_(0)

        self.logfile = logFile
        self.save = saveAgent
        self.load = loadAgent

        self.binName = agentName

        self.optimizer = optim.Adam(self.parameters(), lr=self.learning_rate)
        self.loss = nn.MSELoss()
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.to(self.device)

        if(self.load == "1"):
            self.load_state_dict(T.load(agentName))

    #important! It takes state at current time, action at current time, reward as current time,next_state, done lets us know if episode has ended
    def remember(self,state,action,reward,next_state,done):
        self.memory.append((state,action,reward,next_state,done))

    def forward(self, state):
        x = T.tanh(self.layer1(T.from_numpy(state).float()))
        x = T.tanh(self.layer2(x))
        actions = self.layer3(x)

        return actions

    def actSurrogate(self,state):
        if np.random.rand() <= self.epsilon:  #the bigger epsilon is, the more likely exploration is
            res = (random.randrange(self.action_size))
            return -1,res
            #return random.randrange(self.action_size)
        act_values = self.forward(state)
        maxIndex = np.argmax(act_values.detach().numpy())
        return maxIndex ,act_values

    def act(self,state): #figuring out what action to take given a state
        if np.random.rand() <= self.epsilon:  #the bigger epsilon is, the more likely exploration is
            return random.randrange(self.action_size)
        act_values = self.forward(state)
        return np.argmax(act_values.detach().numpy()) #formerly return np.argmax(act_values.detach().numpy()[0])

    def replay(self,batch_size,log=False):
        #self.optimizer.zero_grad() you had this for the winning run
        minibatch = random.sample(self.memory,batch_size) #randomly sample memories
        f2 = open(self.logfile + "DEBUG.txt","a")

        for state,action,reward,next_state,done in minibatch:
            self.optimizer.zero_grad()
            q_current = self.forward(state)
            q_eval = q_current[action]
            q_next = self.forward(next_state)
            q_target = reward + (self.gamma * T.max(q_next, dim=0)[0]) #original dim=0

            #q_target = reward + (self.gamma * T.max(q_next, dim=0)[0])
            
            loss = self.loss(q_eval,q_target)  #calculate loss and fit the model
            loss.backward()
            self.optimizer.step()

            if(log):
                f2.write("replay  state: " + str(state) + " ,action: " + str(action) + " ,reward: " + str(reward) + " ,next_state: " + str(next_state) + "\n" +
                 " ,q_current: " + str(q_current) + " ,q_eval: " + str(q_eval) + " ,q_next: " + str(q_next) + " ,q_target: " + str(q_target) + "\n")

            if(self.logfile):
                #print("log path!")
                #print(os.path.join(__location__, logFile))
                #print("loss!")
                #print(loss.item())
                f = open(self.logfile,"a")
                f.write(str(loss.item())+"\n")
                f.close()

        f2.close()
        if self.epsilon > self.epsilon_min:
            self.epsilon = self.epsilon * self.epsilon_decay

        print("save state : " + str(self.save))
        print("state dict : " + str(self.state_dict()))
        print("bin name : " + str(self.binName))
        if(self.save):
            T.save(self.state_dict(), self.binName)


