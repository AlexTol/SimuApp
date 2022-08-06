import socket, select
import threading
import time
import redis
import random
import json
from signal import signal, SIGPIPE, SIG_DFL
from models.dqn import DQNAgent
import numpy as np
import os
import requests

agentThyme = True
#global execGet
execGet = False

#global Complete
#global Deny
#global Slow
Complete = {}
Deny = {}
Slow = {}

Complete["A"] = 1
Complete["B"] = 1
Complete["C"]  = 5
Complete["D"]  = 10

Deny["A"] = 2
Deny["B"] = 2
Deny["C"] = 5
Deny["D"] = 10

Slow["A"] = .25
Slow["B"] = .5
Slow["C"] = 1
Slow["D"] = -5

serverPassive = .05 
conPassive = .01

#global prevCPUUsage
prevCPUUsage = {}
#global prevMEMUsage
prevMEMUsage = {}

#global lock
execlock = threading.Lock()
orchlock = threading.Lock()

r = redis.Redis(
    host='localhost',
    port=6379)

def decodeObj(obj):
    dObj = {}
    for key,val in obj.items():
        dObj[key.decode("utf-8")] = val.decode("utf-8")

    return dObj

def correctConSelect(chosenServ,state):
    #get the server
    #choose a con with the correct type, type can be extrapolated from state
    rType = "D"
    if(state[0] == 1):
        rType = "A"
    elif(state[1] == 1):
        rType = "B"
    elif(state[2] == 1):
        rType = "C"

    choices = []

    cons = getContainers({"s" + str(chosenServ):0})["s" + str(chosenServ)]
    for con,conObj in cons.items():
        if(conObj['conType'] == rType):
            choices.append(con)

    if(not choices):
        return 0
    return random.choice(choices)

def randomServConSelect():
    servs = []
    tup = []
    #print("%s\n",r)
    regions = r.smembers("regions")
    for reg in regions:
        regd = reg.decode("utf-8")
        #print("region %s\n",reg)
        rServs = r.smembers(f"{regd}_servers")
        for s in rServs:
            #print("servers %s\n",s)
            servs.append(s.decode("utf-8"))

    ser = random.choice(servs)
    tup.append(ser)
    containers = r.smembers(f"{ser}_containers")
    tup.append(random.choice(tuple(containers)).decode("utf-8"))
    return tup
    
def randomServSelect():
    servs = []
    #print("%s\n",r)
    regions = r.smembers("regions")
    for reg in regions:
        regd = reg.decode("utf-8")
        #print("region %s\n",reg)
        rServs = r.smembers(f"{regd}_servers")
        for s in rServs:
            #print("servers %s\n",s)
            servs.append(s.decode("utf-8"))

    ser = random.choice(servs)
    return ser

def randomConSelect(ser):
    containers = r.smembers(f"{ser}_containers")
    return random.choice(tuple(containers)).decode("utf-8")

def processInput(dat):
    cmdVals = {}
    tuples = dat.split(",")
    for tup in tuples:
        if tup != "" and tup != "\n":
            token = tup.split(":")
            cmdVals[token[0]] = token[1]
    return cmdVals

def calcReqProfit(taskDat):
    global Complete
    global Slow
    global Deny

    profit = 0
    #print("calculating profit for taskDat %s \n",taskDat)

    for req,obj in taskDat.items():
     #   print("agent1 req: %s\n" % req)
      #  print("agent1 obj : %s\n" % obj)
        if(obj["rejected"] == "1"):
       #     print("agent1 reject calc")
            profit -= Deny[obj["type"]]
        elif(obj["timeout"] == "1"):
         #   print("agent1 reject calc")
            profit -= Slow[obj["type"]]
        elif(obj["completed"] == "1"):
        #    print("agent1 reject calc")
            profit += Complete[obj["type"]]

    return profit

def getServers():
    servs = {}
    regions = r.smembers("regions")
    for reg in regions:
        regd = reg.decode("utf-8")
        rServs = r.smembers(f"{regd}_servers")
        for s in rServs:
            servObj = r.hgetall(s.decode("utf-8"))
            servs[s.decode("utf-8")] = decodeObj(servObj)

    return servs;

def checkServerChoice(choice,region):
    serverExists = False 
    correctRegion = False
    mchoice = "s" + str(choice)
    servs = getServers()

    if(mchoice in servs.keys()):
        serverExists = True
        if servs[mchoice]["region"] == region:
             correctRegion = True

    return serverExists,correctRegion

def checkConChoice(conChoice,server,taskType):
    conExists = True
    conTypeCorrect = True
    cons = getContainers({"s" + str(server):0})["s" + str(server)]

    if(not conChoice in cons.keys()):
        conExists = False

    if(cons[conChoice]["conType"] != taskType):
        conTypeCorrect = False

    return conExists,conTypeCorrect

def getServerInfo(serverDict):
    info = {}
    key = list(serverDict.keys())[0]
    cons = getContainers(serverDict)[key]
    #print(cons)

    info['totalCPUUtil'] = 0.0
    cpuUtil = getEntityUtilization(serverDict,"CPU")
    for serv,util in cpuUtil.keys():
        info['totalCPUUtil'] += float(util)
    info['totalCPUUtilA'] = getEntityServerUtilizationType(cons,"A","CPU")
    info['totalCPUUtilB'] = getEntityServerUtilizationType(cons,"B","CPU")
    info['totalCPUUtilC'] = getEntityServerUtilizationType(cons,"C","CPU")
    info['totalCPUUtilD'] = getEntityServerUtilizationType(cons,"D","CPU")
    
    info['totalMEMUtil'] = 0.0
    memUtil = getEntityUtilization(serverDict,"MEM")
    for serv,util in memUtil.keys():
        info['totalMEMUtil'] += float(util)
    info['totalMEMUtilA'] = getEntityServerUtilizationType(cons,"A","MEM")
    info['totalMEMUtilB'] = getEntityServerUtilizationType(cons,"B","MEM")
    info['totalMEMUtilC'] = getEntityServerUtilizationType(cons,"C","MEM")
    info['totalMEMUtilD'] = getEntityServerUtilizationType(cons,"D","MEM")

    #print("info")
    #print(info)
    return info
    

def getContainers(servs):
    mServCons = {}
    for serv,servObj in servs.items():
        servCons = {}
        conList = r.smembers(f"{serv}_containers")
        for con in conList:
            conObj = r.hgetall(con.decode("utf-8"))
            servCons[con.decode("utf-8")] = decodeObj(conObj)

        mServCons[serv] = servCons
    
    return mServCons

def getServerCost(servCons):
    global serverPassive
    global conPassive

    servCosts = {}
    for serv,conDict in servCons.items():
        servCosts[serv] = 0
        servCosts[serv] += serverPassive

        for con,conObj in conDict.items():
            servCosts[serv] += conPassive

    return servCosts

#rtype = resource type (A,B,C,D)
def getEntityServerUtilizationType(cons,rtype,mtype):
    utilizationRate = 0
    typeResource = 0

    for con,conObj in cons.items():
        if(conObj["conType"] == rtype):
            typeResource += float(conObj[f"con{mtype}"])

    curTasks = getTaskData()
    #print("curTasks")
    #print(curTasks)
    conUsage = 0

    if(not curTasks):
        return 0.0

    try:
        for t,tObj in curTasks.items():
            if(tObj["con"] in cons.keys()):
                conUsage += float(tObj[f"t{mtype}"])
    except:
        print("something went wrong here")
        print(curTasks)
        return 0.0

    return conUsage/typeResource

#mtype = CPU or MEM
def getEntityUtilization(servs,mtype):
    utilizationRates = {}
    servResource = {}

    for serv,servObj in servs.items():
        servResource[serv] = float(servObj[f"serv{mtype}"]) #also servMEM

    curTasks = getTaskData()
    servUsage = {}

    if(curTasks):
        for t,tObj in curTasks.items():
            if(not tObj):
                continue
            if(tObj["server"] in servs.keys()):
                if(tObj["server"] in servUsage.keys()):
                    servUsage[tObj["server"]] += float(tObj[f"t{mtype}"])
                else:
                    servUsage[tObj["server"]] = float(tObj[f"t{mtype}"])

    for serv,usage in servUsage.items():
        utilizationRates[serv] = float(usage)/float(servResource[serv])
    
    return utilizationRates

def getEntityDemandChange(mtype):
    global prevCPUUsage
    global prevMEMUsage

    curTasks = getTaskData()
    servDemChance = {}
    servUsage = {}
    for t,tObj in curTasks.items():
        if(tObj["server"] in servUsage.keys()):
            servUsage[tObj["server"]] += float(tObj[f"t{mtype}"])
        else:
            servUsage[tObj["server"]] = float(tObj[f"t{mtype}"])
            #for each server check diff prevCPUUsage and mem

    for serv,usage in servUsage.items():
        if(mtype == "CPU"):
            if(serv in prevCPUUsage.keys()):
                servDemChance[serv] = float(usage) - float(prevCPUUsage[serv])
                prevCPUUsage[serv] = float(usage)
            else:
                servDemChance[serv] = float(usage)
                prevCPUUsage[serv] = float(usage)
        else:
            if(serv in prevMEMUsage.keys()):
                servDemChance[serv] = float(usage) - float(prevMEMUsage[serv])
                prevMEMUsage[serv] = float(usage)
            else:
                servDemChance[serv] = float(usage)
                prevMEMUsage[serv] = float(usage)
        
    return servDemChance

        

def getTaskData():
    taskDat = {}

    currReqs = r.smembers("currentRequests")
    for req in currReqs:
        mReq = r.hgetall(req.decode("utf-8"))
        taskDat[req.decode("utf-8")] = decodeObj(mReq)

    return taskDat
    
def typeToArrRep(mtype):
    if mtype == "A":
        return [1,0,0,0]
    elif mtype == "B":
        return [0,1,0,0]
    elif mtype == "C":
        return [0,0,1,0]
    else:
        return [0,0,0,1]

def regionToArrRep(region):
    if region == "NA":
        return [1,0,0,0,0,0]
    elif region == "SA":
        return [0,1,0,0,0,0]
    elif region == "EU":
        return [0,0,1,0,0,0]
    elif region == "AS":
        return [0,0,0,1,0,0]
    elif region == "AF":
        return [0,0,0,0,1,0]
    else:
        return [0,0,0,0,0,1]

def getServerSenderInfo(state,cmdVals):
    index = 0
    tcpu = 1
    tmem = .5 if (cmdVals['type'] == "A") else 1

    typeArr = typeToArrRep(cmdVals['type'])
    for rep in typeArr:
        state[index] = rep
        index += 1

    state[index] = tcpu
    index += 1
    state[index] = tmem
    index += 1

    regionArr = regionToArrRep(cmdVals['region'])
    for rep in typeArr:
        state[index] = rep
        index += 1

    servs = getServers()
    for serv,servObj in servs.items():
        sO = {}
        sO[serv] = servObj
        servInfo = getServerInfo(sO)
        for key,val in servInfo.items():
            state[index] = val
            index += 1

        regionVals = regionToArrRep(servObj["region"])
        for i in range (0,6):
            state[index] = regionVals[i]
            index += 1

        #if it exists
        state[index] = 1
        index += 1

        
def getContainerSenderInfo(state,cmdVals,schoice): #todo finish this, don't forget to change the server image to have the .ts changes you made
    index = 0

    if(schoice == 0):
        return

    tcpu = 1
    tmem = .5 if (cmdVals['type'] == "A") else 1

    typeArr = typeToArrRep(cmdVals['type'])
    for rep in typeArr:
        state[index] = rep
        index += 1

    state[index] = tcpu
    index += 1
    state[index] = tmem
    index += 1
    
    #getall cons from serv
    servcons = getContainers({"s" + str(schoice):0})

    for serv,conTup in servcons.items():
        for con,cObj in conTup.items():
            #state[index] = servNameToNum(cObj["servName"])
            #index += 1
            state[index] = conNameToNum(con)
            index += 1

            state[index] = 1 if(cObj["conType"] == "A") else 0
            index += 1
            state[index] = 1 if(cObj["conType"] == "B") else 0
            index += 1
            state[index] = 1 if(cObj["conType"] == "C") else 0
            index += 1
            state[index] = 1 if(cObj["conType"] == "D") else 0
            index += 1

            state[index] = getConUtil(cObj["conPort"],"MEM")
            index += 1
            state[index] = getConUtil(cObj["conPort"],"CPU")
            index += 1

            #if it exists
            state[index] = 1
            index += 1

def interpretConChoice(cchoice,schoice):
    servcons = getContainers({"s" + str(schoice):0})
    conTup = servcons["s" + str(schoice)]
    conList = []
    for con,cObj in conTup.items():
        conList.append(con)

    if 0 <= cchoice < len(conList):
        return conNameToNum(conList[cchoice])
    return 0


def servNameToNum(sName):
    return int(sName.split("s")[1])

def conNameToNum(cName):
    return int(cName.split("c")[1])

def getConUtil(port,rtype):
    r = requests.post(f"http://localhost:{port}/simuUtil")

    if(rtype == "CPU"):
        return r.json()["cUtil"]
    else:
        return r.json()["mUTIL"]

def displayEnvState():
    taskData = getTaskData()
    profit = calcReqProfit(taskData)
    servs = getServers()
    servCons = getContainers(servs)
    serverCosts = getServerCost(servCons)
    cpuUtil = getEntityUtilization(servs,"CPU")
    memUtil = getEntityUtilization(servs,"MEM")
    cpuDemChange = getEntityDemandChange("CPU")
    memDemChange = getEntityDemandChange("MEM")

    print("Current EnvironmentState!\n")
    print(f"profit: {profit}\n")
    print("cost: per server\n")
    for serv,costs in serverCosts.items():
        print(f"server : {serv}     cost : {costs}\n")

    print("cpu util: per server\n")
    for serv,util in cpuUtil.items():
        print(f"server : {serv}     cpuUtilization : {util}")

    print("mem util: per server\n")
    for serv,util in memUtil.items():
        print(f"server : {serv}     memUtilization : {util}\n")

    print("cpu dem change : per server\n")
    for serv,demChange in cpuDemChange.items():
        print(f"server : {serv}     cpuDemandChanges : {demChange}\n")

    print("mem dem change : per server\n")
    for serv,demChange in memDemChange.items():
        print(f"server : {serv}     memDemandChanges : {demChange}\n")

def clearFinishedQueries():
    print("clearing finished queries!\n")
    taskData = getTaskData()
    for req,obj in taskData.items():
        if(obj["completed"] == "1" or obj["rejected"] == "1"):
            r.delete(req)
            r.srem("currentRequests",req)

def agentLearn():
        displayEnvState()
        clearFinishedQueries()

def provisionerTime():
    while True:
        time.sleep(1)
        clearFinishedQueries()

def agentTime():
    global agentThyme
    while agentThyme:
        time.sleep(15)
        displayEnvState()
        clearFinishedQueries()

def averageDif(mlist): #credit for simpler way https://stackoverflow.com/questions/47040728/get-average-difference-between-all-numbers-in-a-list-python
    diffs = []
    for i, e in enumerate(mlist):
        for j, f in enumerate(mlist):
            if i != j: diffs.append(abs(e-f))

    return sum(diffs)/len(diffs)


def containerTaskAgentReward(conExists,conTypeCorrect,conType,serverChoice,conChoice,servExists):
    reward = 0
    mFile = os.path.join(path_to_script, "AILOGS/containerTaskAgentReward.txt")
    f = open(mFile,"a")

    servs = getServers()
    if(servExists):
        sname = "s" + str(serverChoice)
        sObj = servs[sname]
        servInfo = getServerInfo({sname:sObj})
    else:
        f.write(f"server doesn't exist,skipping\n")
        f.close()
        return

    if(conExists):
        reward += 1
    else:
        reward -= 1

    if(conTypeCorrect):
        reward += 9
    else:
        reward -= 1

    if(conType != "NA" and servExists):
        cpuUtil = servInfo[f"totalCPUUtil{conType}"]
        memUtil = servInfo[f"totalMEMUtil{conType}"]
    else:
        cpuUtil = 0
        memUtil = 0

    utilAverage = (cpuUtil + memUtil)/2

    utilAverageMultiplier = 1
    if utilAverage >= .9:
        utilAverageMultiplier = 2
    elif utilAverage >= .75:
        utilAverageMultiplier = 1.75
    elif utilAverage >= .5:
        utilAverageMultiplier = 1.5

    if(reward < 0):
        f.write(f"conExists: {conExists},conTypeCorrect: {conTypeCorrect},conChoice :{conChoice},utilAverage: {utilAverage},reward: {reward}\n")
        f.close()
        return reward

    f.write(f"conExists: {conExists},conTypeCorrect: {conTypeCorrect},conChoice :{conChoice},utilAverage: {utilAverage},reward: {utilAverageMultiplier * reward}\n")
    f.close()
    return utilAverageMultiplier * reward

    

def serverTaskAgentReward(serverExists,correctRegion):
    reward = 0
    mFile = os.path.join(path_to_script, "AILOGS/serverTaskAgentReward.txt")
    f = open(mFile,"a")

    if(serverExists):
        reward += 2
    else:
        reward -= 2

    if(correctRegion):
        reward += .5
    else:
        reward -= 0

    servs = getServers()
    utilAverages = []
    for serv,servObj in servs.items():
        servInfo = getServerInfo({serv:servObj})
        numerator = 0
        for key,val in servInfo.items():
            numerator += float(val)
        utilAverages.append(numerator/5)

    utilAverage = 0
    for ave in utilAverages:
        utilAverage += ave

    if(len(utilAverages) > 0):
        utilAverage = utilAverage/len(utilAverages)

    utilAverageMultiplier = 1
    if utilAverage >= .9:
        utilAverageMultiplier = 2
    elif utilAverage >= .75:
        utilAverageMultiplier = 1.75
    elif utilAverage >= .5:
        utilAverageMultiplier = 1.5

    utilAverageDiff = averageDif(utilAverages)

    f.write(f"serverExists: {serverExists}, correctRegion: {correctRegion}, utilAverage: {utilAverage}, utilAverageDiff: {utilAverageDiff},")

    if reward < 0:
        f.write(f"reward: {reward}\n")
        f.close()
        return reward
    else:
        f.write(f"reward: {utilAverageMultiplier * (1 + utilAverageDiff) * reward}\n")
        f.close()
        return (utilAverageMultiplier * (1 + utilAverageDiff) * reward)


def reward1(secondPassed):
    mFile = os.path.join(path_to_script, "AILOGS/reward1.txt")
    f = open(mFile,"a")

    reward = 0
    #add up all the utilization rates
    servs = getServers()
    utilAverages = []
    for serv,servObj in servs.items():
        servInfo = getServerInfo({serv:servObj})
        numerator = 0
        for key,val in servInfo.items():
            numerator += float(val)
        utilAverages.append(numerator/5)

    utilAverage = 0
    for ave in utilAverages:
        utilAverage += ave

    if(len(utilAverages) > 0):
        utilAverage = utilAverage/len(utilAverages)

    f.write("utilAverage: " + str(utilAverage)+",")

    #add profit plus costs
    servCons = getContainers(servs)
    taskData = getTaskData()
    profit = calcReqProfit(taskData)
    f.write("profit: " + str(profit)+",")
    #only calculate the cost everysecond
    serverCosts = getServerCost(servCons)  if(secondPassed) else 0

    reward += float(profit)
    totalCosts = 0
    if(serverCosts != 0):
        for serv,cost in serverCosts.items():
            totalCosts += cost
            reward -= cost
    f.write("totalCosts: " + str(totalCosts)+",")

    clearFinishedQueries()

    utilAverageDiff = averageDif(utilAverages)
    evenDiffMultiplier = 1
    if(utilAverageDiff <= .1):
        evenDiffMultiplier = 3
    elif(utilAverageDiff <= .25):
        evenDiffMultiplier = 2
    elif(utilAverageDiff <= .3):
        evenDiffMultiplier = 1.5
    elif(utilAverageDiff <= .5):
        evenDiffMultiplier = 1.25
    
    f.write("evenDiffMultiplier: " + str(evenDiffMultiplier)+",")

    if(reward <= 0):
        f.write("reward: " + str(reward)+"\n")
        f.close()
        return reward
    else:
        f.write("reward: " + str((evenDiffMultiplier * (2 + utilAverage) * reward))+"\n")
        f.close()
        return (evenDiffMultiplier * (2 + utilAverage) * reward)


def dictToTcpString(cmdVals):
    mid = cmdVals['id']
    mtype = cmdVals['type']
    ttc = cmdVals['timetocomplete']
    region = cmdVals['region']
    deps = cmdVals['deps']

    return f"id:{mid},type:{mtype},timetocomplete:{ttc},region:{region},deps:{deps}"

def handleInput(dat):
    global execlock #how to access global var
    global orchlock
    global execGet
    global orchSock
    global execSock
    global taskAgent
    global episodes
    global episodes2
    global curTime

    cmdVals = processInput(dat)
    if len(cmdVals) == 0:
        print("Empty cmdVals instance py\n")
    elif  cmdVals['cmd'] == "stask":
        with orchlock:
            print("orchsock send!\n")
            orchSock.sendall(b'cmd:agent1Get,buff:buff\r\n')
        print("orchsock done!\n")

        ##deep learning stuff here
        if('taskAgentState' not in locals()):
            taskAgentState = np.zeros(taskAgentStateSize)
            getServerSenderInfo(taskAgentState,cmdVals)

        if('taskAgentState2' not in locals()):
            taskAgentState2 = np.zeros(taskAgentStateSize2)
            getContainerSenderInfo(taskAgentState2,cmdVals,0)
        
        #do the rest of the container agent stuff
        s = taskAgent.act(taskAgentState)
        schoice = s+1
        #print(f"taskAction (server choice): {schoice}")
        c = taskAgent2.act(taskAgentState2)
        cchoice = interpretConChoice(c,schoice)
        #strCChoice = "c" + str(cchoice)
        #c = correctConSelect(schoice,taskAgentState)
        #print(f"container choice: {c}")

        serverExists, correctRegion = checkServerChoice(schoice,cmdVals["region"])
        conExists = False
        conTypeCorrect = False

        #t = randomServConSelect()
        #s = t[0]
        #c = t[1]
        conInfo = decodeObj(r.hgetall(f"c{cchoice}"))
        conPort = 0
        conType = "NA"
        if(conInfo):
            conPort = conInfo['conPort']
            conType = conInfo['conType']
            conExists,conTypeCorrect = checkConChoice("c"+str(cchoice),schoice,cmdVals['type'])
        
        taskString = dictToTcpString(cmdVals)
        with execlock:
            print(f"AGENT 1: cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{schoice},con:{cchoice},buff:buff")
            execSock.sendall(f"cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{schoice},con:{cchoice},buff:buff".encode()) #problem is here, doesn't completely send
            while not execGet:
                pass
            #print("exiting while in agent1\n")
            execGet = False

            prevState = taskAgentState
            prevState2 = taskAgentState2
            #time.sleep(1)
            getServerSenderInfo(taskAgentState,cmdVals) # sets taskAgentState by reference
            getContainerSenderInfo(taskAgentState2,cmdVals,schoice)

            reward = serverTaskAgentReward(serverExists,correctRegion)
            reward2 = containerTaskAgentReward(conExists,conTypeCorrect,conType,schoice,cchoice,serverExists)

            taskAgent.remember(prevState,s,reward,taskAgentState,False)
            episodes += 1
            if(serverExists):
                taskAgent2.remember(prevState2,c,reward2,taskAgentState2,False)
                episodes2 += 1

            if episodes == 32:
                episodes = 0
                taskAgent.replay(32)

            if episodes2 == 32:
                episodes2 = 0
                taskAgent2.replay(32)

        #clearFinishedQueries()
        #agentLearn()
    #print("%s\n",cmdVals)
    elif  cmdVals['cmd'] == "connect":
        with orchlock:
            orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff\r\n')
    elif cmdVals['cmd'] == "execget":
        print("set exec get to true!!!\n")
        execGet = True
    
def second_passed(prevTime):
    return time.time() - prevTime >= 1


#server obtained from https://gist.github.com/logasja/97bddeb84879b30519efb0c66b4db159
def runServer():
    CONNECTION_LIST = []    # list of socket clients
    RECV_BUFFER = 4096 # Advisable to keep it as an exponent of 2
    PORT = 7003
    #signal(SIGPIPE,SIG_DFL)  # you need this for the piping nonsense
         
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # this has no effect, why ?
    #server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", PORT))
    server_socket.listen(10)
 
    # Add server socket to the list of readable connections
    CONNECTION_LIST.append(server_socket)

    t1 = threading.Thread(target=provisionerTime,args=())
    t1.start()
 
    print("agent1 active on port " + str(PORT) + "\n")
 
    while 1:
        # Get the list sockets which are ready to be read through select
        read_sockets,write_sockets,error_sockets = select.select(CONNECTION_LIST,[],[])
 
        for sock in read_sockets:
             
            #New connection
            if sock == server_socket:
                # Handle the case in which there is a new connection recieved through server_socket
                sockfd, addr = server_socket.accept()
                CONNECTION_LIST.append(sockfd)
                print("Client (%s, %s) connected" % addr)
                 
            #Some incoming message from a client
            else:
                # Data recieved from client, process it
                try:
                    #In Windows, sometimes when a TCP program closes abruptly,
                    # a "Connection reset by peer" exception will be thrown
                    data = sock.recv(RECV_BUFFER)
                    strDat = data.decode("utf-8")
                    #print("agent1 dat : %s\n",strDat)
                    batches = strDat.split(",buff:buff")
                    #get any tasks rejected
                    for batch in batches:
                        tRep = threading.Thread(target=handleInput,args=(batch,)) #appearently the extra comma should fix the issue, try it out
                        tRep.start()
                        #handleInput(batch)
                    #orchSock.sendall(b'cmd:agent1Get,buff:buff')
                 
                # client disconnected, so remove from socket list
                except:
                    broadcast_data(sock, "Client (%s, %s) is offline" % addr)
                    print("Client (%s, %s) is offline" % addr)
                    sock.close()
                    CONNECTION_LIST.remove(sock)
                    continue
         
    server_socket.close()


#todo idea: make agent time happen everytime 
#HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
#PORT = 7003  # Port to listen on (non-privileged ports are > 1023)

print("agent1 to orch!\n")
orchSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
orchSock.connect(('localhost', 7002))
orchSock.setblocking(0)
obsSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
obsSock.connect(('localhost', 7001))
obsSock.setblocking(0)
execSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
execSock.connect(('localhost', 7000))
execSock.setblocking(0)

curTime = time.time()
#orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff')
#todo figure out dimension of server and task inputs
#Task_dims + (num_servers * server_dims)
taskAgentStateSize = 12 + (30 * 17)
taskAgentActionSize = 30
taskAgentState = np.zeros(taskAgentStateSize)

taskAgentStateSize2 =  12 + (7 * 50)
taskAgentActionSize2 = 50
taskAgentState2 = np.zeros(taskAgentStateSize2)

episodes = 0
episodes2 = 0
path_to_script = os.path.dirname(os.path.abspath(__file__))
mFile = os.path.join(path_to_script, "AILOGS/t1_loss.txt")
mFile2 = os.path.join(path_to_script, "AILOGS/t2_loss.txt")
taskAgent = DQNAgent(taskAgentStateSize,taskAgentActionSize,mFile)
taskAgent2 = DQNAgent(taskAgentStateSize2,taskAgentActionSize2,mFile2)


mt = threading.Thread(target=runServer,args=())
mt.start()
#runServer()
