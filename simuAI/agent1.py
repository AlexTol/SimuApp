import socket, select
import threading
import time
import redis
import random
import json
from signal import signal, SIGPIPE, SIG_DFL
from models.dqn import DQNAgent
from models.scheduleNet import ScheduleNet
import numpy as np
import os
import requests

agentThyme = True
#global execGet
execGet = False
execGet2 = False
cDelConfirmed = False
cAddConfirmed = False
provisioningInAction = False
provisioningTriggered = False
schedulerWorking = False
inARow = 0

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
execlock2 = threading.Lock()
orchlock = threading.Lock()

r = redis.Redis(
    host='localhost',
    port=6379)

def decodeObj(obj):
    dObj = {}
    for key,val in obj.items():
        dObj[key.decode("utf-8")] = val.decode("utf-8")

    return dObj

def switchProvisioner(rewards):
    global schedulerWorking
    global inARow

    numerator = 0
    for i in range(0,len(rewards)):
        if(rewards[i] > 0):
            numerator += 1

    triggerRatio = numerator/len(rewards)
    print("triggerRatio : " + str(triggerRatio))
    if(triggerRatio > 0):
        inARow += 1
        if(inARow >= 0):
            schedulerWorking = True
    else:
        inARow = 0

def correctservSelect(cmdVals):
    regions = cmdVals['region']
    servs = getServers()
    elligibleServs = []
    
    for serv,sObj in servs.items():
        if(sObj["region"] == regions):
            elligibleServs.append(serv)

    return random.choice(elligibleServs).split("s")[1]

    

def correctConSelect(chosenServ,cmdVals):
    #get the server
    #choose a con with the correct type, type can be extrapolated from state
    rType = cmdVals['type']

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

def getTimedOutCount(taskDat,servNum):
    count = 0
    for req,obj in taskDat.items():
        if(obj["timeout"] == "1" and obj["server"] == servNum):
            count += 1

    return count

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
        try:
            if(conObj["conType"] == rtype):
                typeResource += float(conObj[f"con{mtype}"])
        except:
            print("current con not available \n" +
            " con: " + str(con) + " " + str(conObj))

    if(typeResource == 0):
        return 0.0

    curTasks = getTaskData()
    #print("curTasks")
    #print(curTasks)
    conUsage = 0

    if(not curTasks):
        return 0.0

    for t,tObj in curTasks.items():
        try:
            if(tObj["con"] in cons.keys()):
                conUsage += float(tObj[f"t{mtype}"])
        except:
            print("current task not available \n" +
            " currentTasks: " + str(curTasks) + "\n" +
            + " task in question: " + str(t) + " " + str(tObj))


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

def typeToIntRep(mtype):
    if mtype == "A":
        return 1
    elif mtype == "B":
        return 2
    elif mtype == "C":
        return 3
    else:
        return 4

def regionToIntRep(region):
    if region == "NA":
        return 1
    elif region == "SA":
        return 2
    elif region == "EU":
        return 3
    elif region == "AS":
        return 4
    elif region == "AF":
        return 5
    else:
        return 6

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
    for rep in regionArr:
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

def scheduleLayer1Info(state,cmdVals,servTuple):
    index = 0
    #state[index] = 0
    #index += 1

    tRegionVal = regionToArrRep(cmdVals['region'])
    for i in range(0,len(tRegionVal)):
        state[index] = tRegionVal[i]
        index += 1

    servObj = list(servTuple.values())[0]
    sRegionVal = regionToArrRep(servObj["region"])
    for i in range(0,len(sRegionVal)):
        state[index] = sRegionVal[i]
        index += 1


def scheduleLayer2Info(state,cmdVals,con,cObj):
    index = 0
    #state[index] = 0
    #index += 1

    #tType = typeToIntRep(cmdVals['type'])
    #state[index] = tType
    #index += 1
    tTypeReps = typeToArrRep(cmdVals['type'])
    for i in range(0,len(tTypeReps)):
        state[index] = tTypeReps[i]
        index += 1

    #cType = typeToIntRep(cObj["conType"])
    #state[index] = cType
    #index += 1
    cTypeReps = typeToArrRep(cObj["conType"])
    for i in range(0,len(cTypeReps)):
        state[index] = cTypeReps[i]
        index += 1

def scheduleLayer3Info(state,chosenCon,chosenConObj,sCons):
    index = 0
    conNum = chosenCon.split("c")[1]
    state[index] = getConUtil2(conNum,"CPU")
    index += 1

    typeUtilCPU = []
    for cName,cObj in sCons.items():
        if(len(cObj) == 0):
            continue
        if(cObj["conType"] == chosenConObj["conType"]):
            typeUtilCPU.append(getConUtil2(cName.split("c")[1],"CPU"))
    typeUtilCPUDiff = averageDif(typeUtilCPU)
    state[index] = typeUtilCPUDiff
    index +=1

    state[index] = getConUtil2(conNum,"MEM")
    index += 1

    typeUtilMEM = []
    for cName,cObj in sCons.items():
        if(len(cObj) == 0):
            continue
        if(cObj["conType"] == chosenConObj["conType"]):
            typeUtilMEM.append(getConUtil2(cName.split("c")[1],"MEM"))
    typeUtilMEMDiff = averageDif(typeUtilMEM)
    state[index] = typeUtilMEMDiff
    index +=1


def getContainerProvisionerInfo(state,serv,sObj):
        taskDat = getTaskData()
        info = getServerInfo({serv:sObj})
        sNum = servNameToNum(serv)
        timeouts = getTimedOutCount(taskDat,sNum)

        state[0] =  info['totalCPUUtilA'] 
        state[1] =  info['totalCPUUtilB'] 
        state[2] =  info['totalCPUUtilC'] 
        state[3] =  info['totalCPUUtilD'] 
        state[4] = info['totalMEMUtilA']
        state[5] = info['totalMEMUtilB']
        state[6] = info['totalMEMUtilC']
        state[7] = info['totalMEMUtilD']

        state[8] = 0
        state[9] = 0
        state[10] = 0
        state[11] = 0

        servcons = getContainers({serv:sObj})

        for serv,conTup in servcons.items():
            for con,cObj in conTup.items():
                if(len(cObj) == 0):
                    continue

                if(cObj["conType"] == "A"):
                    state[8] += 1
                elif(cObj["conType"] == "B"):
                    state[9] += 1
                elif(cObj["conType"] == "C"):
                    state[10] += 1
                else:
                    state[11] += 1

        state[12] = timeouts
        state[13] = sObj["availableCPU"]
        state[14] = sObj["availableMEM"]

        
def getContainerSenderInfo(state,cmdVals,schoice):
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

            state[index] = getConUtil2(con.split("c")[1],"MEM")
            index += 1
            state[index] = getConUtil2(con.split("c")[1],"CPU")
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

    try:
        print(f"request to http://localhost:{port}/simuUtil \n")
        r = requests.post(f"http://localhost:{port}/simuUtil")
    except:
        print(f"con on port {port} no longer exists")
        return 0


    if(rtype == "CPU"):
        cpuutil = r.json()["cUtil"]
        print(f"!CPU UTIL: {cpuutil}")
        if(cpuutil == None):
            cpuutil = 0

        return cpuutil
    else:
        memutil = r.json()["mUTIL"]
        print(f"!MEM UTIL: {memutil}")
        if(memutil == None):
            memutil = 0

        return memutil

def getConUtil2(conNum,rType):
    currReqs = r.smembers("currentRequests")
    utilNum = 0
    for req in currReqs:
        mReq = r.hgetall(req.decode("utf-8"))
        reqObj = decodeObj(mReq)
        #print("reqObj " + str(reqObj))
        #print("conNum: " + str(conNum))
        if(len(reqObj) != 0):
            if(reqObj["con"] == conNum):
                if(rType == "CPU"):
                    utilNum += float(reqObj["tCPU"])
                else:
                    utilNum += float(reqObj["tMEM"])


    con = r.hgetall("c" + str(conNum))
    mCon = decodeObj(con)

    if(len(mCon) != 0):
        if(rType == "CPU"):
            util = utilNum/(float(mCon["conCPU"]))
        else:
            util = utilNum/(float(mCon["conMEM"]))
    else: #if con no longer exists then util is zero
        util = 0

    return util

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
    global provisioningInAction
    global provisioningTriggered
    global schedulerWorking
    global provOn

    count = 0
    firstTimeDelay = 10
    while True:
        time.sleep(5)
        clearFinishedQueries()
        count += 1
        if(provisioningTriggered): #cheesy way of running this every 30 secs
            provisioningInAction = True
            if(schedulerWorking):
                if(provOn == "1"):
                    conProvisioningTime(15)
            count = 0
            #irstTimeDelay = 0
            provisioningTriggered = False
            provisioningInAction = False

def agentTime():
    global agentThyme
    while agentThyme:
        time.sleep(15)
        displayEnvState()
        clearFinishedQueries()

def averageDif(mlist): #credit for simpler way https://stackoverflow.com/questions/47040728/get-average-difference-between-all-numbers-in-a-list-python
    if(len(mlist) == 0):
        return 0
    
    diffs = []
    for i, e in enumerate(mlist):
        for j, f in enumerate(mlist):
            if i != j: diffs.append(abs(e-f))

    if(len(diffs) == 0):
        return 0
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

def calcUtilPenalty(util,count):
    softener = 1
    if(count == 1):
        softener = .7

    if(util <= .1):
        return 1 * softener
    elif(util <= .3):
        return .5
    elif(util <= .6):
        return .2
    elif(util <= .75):
        return .15
    elif(util <= .8):
        return .1
    elif(util <= .95):
        return 0
    else:
        return .3

def utilScore(util,count):
    if(util <= .15):
        if(count > 8):
            return [1,0,15]
        else:
            return [8,0,0]
    elif(util <= .3):
        return [3,1,10]
    elif(util <= .5):
        return [9,6,8]
    elif(util <= .75):
        return [15,8,6]
    elif(util <= .9):
        return [4,12,1]
    else:
        return [0,15,0]


def conProvisionerReward(serv,sObj,poorDeprovision,poorProvision,timeouts,prevAction):
    mFile = os.path.join(path_to_script, "AILOGS/provisionreward1.txt")
    f = open(mFile,"a")
    conCount = len(getContainers({serv:0})[serv])

    info = getServerInfo({serv:sObj})

    if(poorDeprovision or poorProvision):
        return 0
        f.write("server: " + str(serv) + " ,choice: " + str(prevAction) + " ,totalMEMUTILA: " + str(info['totalMEMUtilA']) + " ,totalMEMUTILB: " + str(info['totalMEMUtilB'])
        + " ,totalMEMUTILCs: " + str(info['totalMEMUtilC']) + " ,totalMEMUTILD: " + str(info['totalMEMUtilD']) + " ,totalCPUUTILA: " + str(info['totalCPUUtilA']) + " ,totalCPUUTILB: " + str(info['totalCPUUtilB'])
        + " ,totalCPUUTILC: " + str(info['totalCPUUtilC']) + " ,totalCPUUTILD: " + str(info['totalCPUUtilD']) + " ,conCount: " + str(conCount) + " ,reward: " + str(0) + "\n")

    reward = 0
    if(prevAction == 0):
        memBase = info['totalMEMUtilA'] + info['totalMEMUtilB'] + info['totalMEMUtilC'] + info['totalMEMUtilD']
        cpuBase = info['totalCPUUtilA'] + info['totalCPUUtilB'] + info['totalCPUUtilC'] + info['totalCPUUtilD']

        reward = utilScore((memBase + cpuBase)/2,conCount)[0]
    elif(prevAction == 1):
        memBase = info['totalMEMUtilA']
        cpuBase = info['totalCPUUtilA']

        reward = utilScore((memBase + cpuBase)/2,conCount)[1]
    elif(prevAction == 2):
        memBase = info['totalMEMUtilB']
        cpuBase = info['totalCPUUtilB']

        reward = utilScore((memBase + cpuBase)/2,conCount)[1]
    elif(prevAction == 3):
        memBase = info['totalMEMUtilC']
        cpuBase = info['totalCPUUtilC']

        reward = utilScore((memBase + cpuBase)/2,conCount)[1]
    elif(prevAction == 4):
        memBase = info['totalMEMUtilD']
        cpuBase = info['totalCPUUtilD']

        reward = utilScore((memBase + cpuBase)/2,conCount)[1]
    elif(prevAction == 5):
        memBase = info['totalMEMUtilA']
        cpuBase = info['totalCPUUtilA']

        reward = utilScore((memBase + cpuBase)/2,conCount)[2]
    elif(prevAction == 6):
        memBase = info['totalMEMUtilB']
        cpuBase = info['totalCPUUtilB']

        reward = utilScore((memBase + cpuBase)/2,conCount)[2]
    elif(prevAction == 7):
        memBase = info['totalMEMUtilC']
        cpuBase = info['totalCPUUtilC']

        reward = utilScore((memBase + cpuBase)/2,conCount)[2]
    elif(prevAction == 8):
        memBase = info['totalMEMUtilD']
        cpuBase = info['totalCPUUtilD']

        reward = utilScore((memBase + cpuBase)/2,conCount)[2]

    timeoutPenalty = 1
    if(timeouts <= 5):
        timeoutPenalty = .95
    elif(timeouts <= 10):
        timeoutPenalty = .9
    elif(timeouts <= 20):
        timeoutPenalty = .8
    else:
        timeoutPenalty = .5

    f.write("server: " + str(serv) + " ,choice: " + str(prevAction) + " ,totalMEMUTILA: " + str(info['totalMEMUtilA']) + " ,totalMEMUTILB: " + str(info['totalMEMUtilB'])
    + " ,totalMEMUTILCs: " + str(info['totalMEMUtilC']) + " ,totalMEMUTILD: " + str(info['totalMEMUtilD']) + " ,totalCPUUTILA: " + str(info['totalCPUUtilA']) + " ,totalCPUUTILB: " + str(info['totalCPUUtilB'])
    + " ,totalCPUUTILC: " + str(info['totalCPUUtilC']) + " ,totalCPUUTILD: " + str(info['totalCPUUtilD']) + " ,conCount: " + str(conCount) + " ,reward: " + str(reward * timeoutPenalty) + "\n")
    
    return reward * timeoutPenalty

def getConOfLowestUtilType(serv,mtype):
    #todo figure this out
    botUtil = 1000
    botCon = "blah"
    #getConUtil(chosenConObj["conPort"],"CPU")
    cons = getContainers({serv:0})[serv]
    for con,cObj in cons.items():
        print("con: " + str(con))
        print("cObj: " + str(cObj))
        if(len(cObj) == 0):
            continue
        if(cObj["conType"] != mtype):
            continue

        cpuUtil = getConUtil2(con.split("c")[1],"CPU")
        print("conUtil CPU : " + str(cpuUtil))

        memUtil = getConUtil2(con.split("c")[1],"MEM")
        print("conUtil MEM : " + str(memUtil))
        
        util = (cpuUtil + memUtil)/2
        if(util < botUtil):
            botCon = con

    return botCon

def waitDel():
    global cDelConfirmed
    print("going into del\n")
    while not cDelConfirmed:
        #print("cDelConfirmed " + str(cDelConfirmed))
        pass
    cDelConfirmed = False
    print("going out of del\n")

def waitAdd():
    global cAddConfirmed

    print("going into add\n")
    while not cAddConfirmed:
        #print("cAddConfirmed " + str(cAddConfirmed))
        pass
    cAddConfirmed = False
    print("going out of add\n")

def execConProvChoice(choice,state,serv,sObj):
    global execlock2
    global execSock2
    global execGet2
    global cAddConfirmed


    poorDeprovision = False
    poorProvision = False
    waitadd = False
    waitdel = False
    #cmd:createCon,servName:s1,servPort:8000,conName:c1,conPort:9000,conType:C,buff:buff
    #cmd:deleteCon,servName:s1,servPort:8000,conName:c3,buff:buff
    servPort = sObj["servPort"]
    print("EXECCONPROVECHOICE HERE, choice " + str(choice))
    with execlock2:
        if(choice == 1):
            if(state[13] < 2 or state[14] < 1):
                poorProvision = True
            cmd = f"cmd:createCon,servName:{serv},servPort:{servPort},conName:c1,conPort:9000,conType:A,agent:y,buff:buff"
            waitadd = True
        elif(choice == 2):
            if(state[13] < 2 or state[14] < 2):
                poorProvision = True
            cmd = f"cmd:createCon,servName:{serv},servPort:{servPort},conName:c1,conPort:9000,conType:B,agent:y,buff:buff"
            waitadd = True
        elif(choice == 3):
            if(state[13] < 4 or state[14] < 4):
                poorProvision = True
            cmd = f"cmd:createCon,servName:{serv},servPort:{servPort},conName:c1,conPort:9000,conType:C,agent:y,buff:buff"
            waitadd = True
        elif(choice == 4):
            if(state[13] < 8 or state[14] < 8):
                poorProvision = True
            cmd = f"cmd:createCon,servName:{serv},servPort:{servPort},conName:c1,conPort:9000,conType:D,agent:y,buff:buff"
            waitadd = True
        elif(choice == 5):
            print("A Count: " + str(state[8]) + " ,equals? : " + str(state[8] == 1)) #todo cast this to float, maybe check if the state == 1
            if(state[8] == 1):
                poorDeprovision = True
            con = getConOfLowestUtilType(serv,"A")
            cmd = f"cmd:deleteCon,servName:{serv},servPort:{servPort},conName:{con},conType:A,buff:buff"
            waitdel = True
        elif(choice == 6):
            print("B Count: " + str(state[9]) + " ,equals? : " + str(state[9] == 1))
            if(state[9] == 1):
                poorDeprovision = True
            con = getConOfLowestUtilType(serv,"B")
            cmd = f"cmd:deleteCon,servName:{serv},servPort:{servPort},conName:{con},conType:B,buff:buff"
            waitdel = True
        elif(choice == 7):
            print("C Count: " + str(state[10]) + " ,equals? : " + str(state[10] == 1))
            if(state[10] == 1):
                poorDeprovision = True
            con = getConOfLowestUtilType(serv,"C")
            cmd = f"cmd:deleteCon,servName:{serv},servPort:{servPort},conName:{con},conType:C,buff:buff"
            waitdel = True
        elif(choice == 8):
            print("D Count: " + str(state[11]) + " ,equals? : " + str(state[11] == 1))
            if(state[11] == 1):
                poorDeprovision = True
            con = getConOfLowestUtilType(serv,"D")
            cmd = f"cmd:deleteCon,servName:{serv},servPort:{servPort},conName:{con},conType:D,buff:buff"
            waitdel = True
        else:
            return False,False

        if(not poorDeprovision and not poorProvision):
            print("poorDeprovision: " + str(poorDeprovision) + "poorProvision:" + str(poorProvision) + " ,cAddConfirmed: " + str(cAddConfirmed) +" , cmd: " + str(cmd))
            execSock2.sendall(cmd.encode())

            #while not execGet2:
            #    pass
            #execGet2 = False

            #if(waitadd):
            #    waitAdd()
            #elif(waitdel):
            #    waitDel()

    print("EXECCONPROVECHOICE HERE2, choice " + str(choice))
    return poorDeprovision,poorProvision


def scheduleReward1(choices,servNames,servObjs,region):
    rewards = []
    properlyProvisioned = {}
    mFile = os.path.join(path_to_script, "AILOGS/schedreward1.txt")
    f = open(mFile,"a")

    for i in range(0,len(choices)):
        rewards.append(0)
        properlyProvisioned[servNames[i]] = 0
        if(choices[i] == 1 and region == servObjs[i]["region"]):
            rewards[i] = 10
            properlyProvisioned[servNames[i]] = 1
        elif(choices[i] == 0 and region != servObjs[i]["region"]):
            rewards[i] = 1

        f.write("choice: " + str(choices[i]) + " ,server: " + str(servNames[i])+ ",serverRegion: " + str(servObjs[i]["region"]) + ",Region: " + str(region) + ",Reward: " + 
        str(rewards[i])  + "\n")

    f.close()
    return rewards,properlyProvisioned

def scheduleReward2(choices,cons,mtype,correctlyChosen):
    rewards = {}
    properlyProvisioned = {}
    mFile = os.path.join(path_to_script, "AILOGS/schedreward2.txt")
    f = open(mFile,"a")

    maxReward = 8 #len(cons) * 2
    denominator = (len(cons) - 1)
    if(denominator == 0):
        denominator = 1
    minReward = 2.2 #(maxReward  * .6)/denominator

    for con,cObj in cons.items():
        rewards[con] = 0
        #properlyProvisioned[conNames[i]] = 0
        if(choices[con] == 1 and cons[con]["conType"] == mtype):
            rewards[con] = maxReward
        #    properlyProvisioned[conNames[i]] = 1
        elif(choices[con] == 0 and cons[con]["conType"] != mtype):
            rewards[con] = minReward
         #   properlyProvisioned[conNames[i]] = 1

        f.write("con: " + str(con) + " ,choice: " + str(choices[con]) + " ,conType: " + str(cons[con]["conType"]) 
        + " ,taskType: " + str(mtype) + " ,reward: " + str(rewards[con]) + " ,correctlyChosen: " + str(correctlyChosen) + "\n")

    f.close()
    return rewards,properlyProvisioned

def scheduleReward3(chosenConState,chosenConName):
    reward = 0
    mFile = os.path.join(path_to_script, "AILOGS/schedreward3.txt")
    f = open(mFile,"a")

    if(chosenConState != ""):
        memUtilDiff = chosenConState[3]
        cpuUtilDiff = chosenConState[1]
    else:
        memUtilDiff = 0
        cpuUtilDiff = 0


    if memUtilDiff <= .1:
        reward += 1
    elif memUtilDiff <= .25:
        reward += .5
    elif memUtilDiff <= .5:
        reward += .25
    else:
        reward += 0

    if cpuUtilDiff <= .1:
        reward += 1
    elif cpuUtilDiff <= .25:
        reward += .5
    elif cpuUtilDiff <= .5:
        reward += .25
    else:
        reward += 0

    f.write("ChosenCon: " + chosenConName + " ,memDiff: " + str(memUtilDiff) + " ,cpuDiff: " + str(cpuUtilDiff) + " ,reward: " + str(reward) + "\n" ) #finish this log also remember to figure out the state[0] = 1 where we only want to do that if a good result was had
    f.close()

    return reward
    

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

def perfectTaskScheduling(cmdVals):
    global execlock 

    s = correctservSelect(cmdVals)
    c = correctConSelect(s,cmdVals)

    conInfo = decodeObj(r.hgetall(f"{c}"))
    conPort = 0
    conType = "NA"
    if(conInfo):
        conPort = conInfo['conPort']
        conType = conInfo['conType']
        conExists,conTypeCorrect = checkConChoice(str(c),s,cmdVals['type'])
        
    cVector = c.split("c")[1]

    taskString = dictToTcpString(cmdVals)
    with execlock:
        print(f"AGENT 1: cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{s},con:{cVector},buff:buff")
        execSock.sendall(f"cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{s},con:{cVector},buff:buff".encode()) 



def zeroEncodeAgentTime(cmdVals):
    global execlock #how to access global var
    global orchlock
    global execGet
    global orchSock
    global execSock
    global taskAgent
    global episodes
    global episodes2
    global curTime

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
        print("exiting while in agent1\n")
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

def scheduleNetTime(cmdVals,l1_size,l2_size,l3_size):
    global execlock #how to access global var
    global orchlock
    global execGet
    global orchSock
    global execSock
    global curTime
    global scheduleAgent 
    global episodes3

    with orchlock:
        print("orchsock send!\n")
        orchSock.sendall(b'cmd:agent1Get,buff:buff\r\n')
    print("orchsock done!\n")

    servs = getServers()
    layer1List = []
    servNames = []
    servObjs = []

    for serv,servObj in servs.items():
        s = {}
        s[serv] = servObj
        state = np.zeros(l1_size) #l1_size should be 12 + 16, maybe more globals for the size

        scheduleLayer1Info(state,cmdVals,s)

        layer1List.append(state)
        servNames.append(serv)
        servObjs.append(servObj)

    choices1,sChoice = scheduleAgent.act1(layer1List,servNames) # retrieve output from this and convert into containers. Also remember it
    #print("schoice " + sChoice)
    cons = getContainers({str(sChoice):0})[str(sChoice)]
    #print(cons)

    layer2List = {}
    conObjs = []
    conNames = []
    #j = 0
    for con,conObj in cons.items():
        state2 = np.zeros(l2_size)
        
        if(len(conObj) != 0):
            scheduleLayer2Info(state2,cmdVals,con,conObj)
        
        conObjs.append(conObj)
        conNames.append(con)
        #print("ConObj: " + str(conObj) + " ,state2: " + str(state2) + " ,index: " + str(j))
        layer2List[con] = state2
        #j += 1

    #print("layer2list 1 : " + str(layer2List))
    #print(layer2List)
    choices2,chosenConStates,chosenCons = scheduleAgent.act2(layer2List,cons)
    #print(chosenCons)

    layer3List = {}
    for con,cObj in chosenCons.items():
        state3 = np.zeros(l3_size)
        scheduleLayer3Info(state3,con,cObj,cons)
        layer3List[con] = state3

    choices3,chosenCon = scheduleAgent.act3(layer3List,chosenCons)

    #chosenConStr = "c" + str(int(chosenCon))
    #print(chosenConStr)
    conInfo = decodeObj(r.hgetall(f"{chosenCon}"))
    #print(conInfo)
    if(len(conInfo) != 0):
        conPort = conInfo['conPort']
        conType = conInfo['conType']
    else:
        conPort = 100000
        conType = 100000

    #todo change the next states so that the provisioned correctly dim is set to 1
    taskString = dictToTcpString(cmdVals)
    rewardVector = []
    with execlock:
        serverNum = sChoice.split("s")[1] #just use a number when specifying the server
        conNum = chosenCon.split("c")[1]
        print(f"AGENT 1: cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{serverNum},con:{conNum},buff:buff")
        execSock.sendall(f"cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{serverNum},con:{conNum},buff:buff".encode()) #problem is here, doesn't completely send
        while not execGet:
            pass
        execGet = False

        rewards1,properlyProvisioned = scheduleReward1(choices1,servNames,servObjs,cmdVals['region'])
        servs2 = getServers()
        servsNextState = []
        for serv,servObj in servs2.items():
            s2 = {}
            s2[serv] = servObj
            state = np.zeros(l1_size) #l1_size should be 12 + 16, maybe more globals for the size

            scheduleLayer1Info(state,cmdVals,s)
            #state[0] = properlyProvisioned[serv]
            servsNextState.append(state)
        #get consNextState
        #todo send decision to executor
        correctlyChosen = False
        for con,dimlist in choices2.items():
            if(choices2[con] == 1 and (chosenCons[con]["conType"]) == cmdVals['type']):
                correctlyChosen = True
            elif(choices2[con] == 1 and (chosenCons[con]["conType"]) != cmdVals['type']):
                correctlyChosen = False
                break

        rewards2,properlyProvisioned = scheduleReward2(choices2,cons,cmdVals['type'],correctlyChosen)

        for con,reward in rewards2.items():
            rewardVector.append(reward)

        cons2 = getContainers({str(sChoice):0})[str(sChoice)]
        consNextState = {}
        chosenConNextState = ""
        #chosenConObjs = []
        #chosenConNames = []
        for con,conObj in cons2.items():
            state2 = np.zeros(l2_size)

            if(len(conObj) != 0):
                scheduleLayer2Info(state2,cmdVals,con,conObj)
            #state2[0] = properlyProvisioned[con]

            if(con == chosenCon):
                state3 = np.zeros(l3_size)
                chosenConObj = conObj
                #chosenConObjs.append(chosenConObj)
                scheduleLayer3Info(state3,chosenCon,chosenConObj,cons2)
                chosenConNextState = state3 
            
            consNextState[con] = state2

        chosenConsNextState = {}
        for con,cObj in chosenCons.items():
            state3 = np.zeros(l3_size)
            scheduleLayer3Info(state3,con,cObj,cons2)
            chosenConsNextState[con] = state3
    

        #rewards1 = scheduleReward1(choices1,servNames,servObjs,cmdVals['region'])
        scheduleAgent.remember(1,layer1List,choices1,rewards1,servsNextState)

        #rewards2 = scheduleReward2(choices2,conNames,conObjs,cmdVals['type'])
        scheduleAgent.remember(2,layer2List,choices2,rewards2,consNextState)

        reward3 = scheduleReward3(chosenConNextState,chosenCon)
        rewards3 = {}
        for con,cObj in chosenCons.items():
            rewards3[con] = reward3

        scheduleAgent.remember(3,layer3List,choices3,rewards3,chosenConsNextState) #todo look into reforming this

        episodes3 += 1
        if(episodes3 == 10):
            switchProvisioner(rewardVector)
            rewardVector = []
            episodes3 = 0
            scheduleAgent.replay(10)

def conProvisioningTime(size): #todo complete, double check the parallelism on this too....
    global episodes4
    global conProvisioningAgent
    global prevServStates 
    global prevServActs
    global prevServRewards
    global prevServPDeprovs
    global prevServPProvs
    
    servs = getServers()
    servActs = {}
    poorDeprovisions = {}
    poorProvisions = {}
    #for serv,state in prevServStates.items():
    #    choice = conProvisioningAgent.act(state)
    #    servActs[serv] = choice
    #    pDeprovision = execConProvChoice(choice,state,serv,servs[serv])
    #    poorDeprovisions[serv] = pDeprovision

    servStates = {}
    servRewards = {}
    for serv,sObj in servs.items():
        state = np.zeros(size)

        getContainerProvisionerInfo(state,serv,sObj)

        servStates[serv] = state
        choice = conProvisioningAgent.act(state)
        servActs[serv] = choice
        pDeprovision,pProvision = execConProvChoice(choice,state,serv,sObj)
        poorDeprovisions[serv] = pDeprovision
        poorProvisions[serv] = pProvision

        if(prevServActs == "none" or len(prevServActs) == 0):
            prevAction = "none"
        else:
            #print(prevServActs)
            prevAction = prevServActs[serv]

        if(len(prevServPDeprovs) == 0):
            poorDeprov = False
        else:
            poorDeprov = prevServPDeprovs[serv]

        if(len(prevServPProvs) == 0):
            poorProv = False
        else:
            poorProv = prevServPProvs[serv]

        reward = conProvisionerReward(serv,sObj,poorDeprov,poorProv,state[12],prevAction)
        servRewards[serv] = reward
        if(serv in prevServStates.keys() and (prevServActs != "none" and len(prevServActs) > 0)):
            conProvisioningAgent.remember(prevServStates[serv],prevServActs[serv],prevServRewards[serv],state,False)

    prevServActs = servActs
    prevServStates = servStates
    prevServRewards = servRewards
    prevServPDeprovs = poorDeprovisions
    prevServPProvs = poorProvisions



def handleInput(dat):
    global execlock #how to access global var
    global orchlock
    global execGet
    global execGet2
    global cAddConfirmed
    global cDelConfirmed
    global orchSock
    global execSock
    global taskAgent
    global scheduleAgent 
    global episodes
    global episodes2
    global episodes3
    global curTime
    global provisioningInAction
    global provisioningTriggered
    global zeroEOn
    global schedOn

    cmdVals = processInput(dat)
    if len(cmdVals) == 0:
        print("Empty cmdVals instance py\n")
    elif  cmdVals['cmd'] == "stask":
        while provisioningInAction:
            pass
        if(zeroEOn == "1"):
            zeroEncodeAgentTime(cmdVals)
        elif(schedOn == "1"):
            scheduleNetTime(cmdVals,12,8,4)
        else:
            perfectTaskScheduling(cmdVals)
    elif  cmdVals['cmd'] == "connect":
        with orchlock:
            orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff\r\n')
    elif cmdVals['cmd'] == "execget":
        print("set execget to true!!!\n")
        execGet = True
    elif cmdVals['cmd'] == "execget2":
        print("set execget2 to true!!!\n")
        execGet2 = True
    elif cmdVals['cmd'] == "cAddConfirmed":
        print("set cAddConfirmed to true!!!\n")
        cAddConfirmed = True
    elif cmdVals['cmd'] == "cDelConfirmed":
        print("set cDelConfirmed to true!!!\n")
        cDelConfirmed = True
    elif cmdVals['cmd'] == "triggerprovision":
        print("set triggerprovision to true!!!\n")
        provisioningTriggered = True
    
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
    server_socket.listen(1000)
 
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
                    #broadcast_data(sock, "Client (%s, %s) is offline" % addr)
                    print("Client (%s, %s) is offline" % addr)
                    sock.close()
                    CONNECTION_LIST.remove(sock)
                    continue
         
    server_socket.close()


#todo idea: make agent time happen everytime 
#HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
#PORT = 7003  # Port to listen on (non-privileged ports are > 1023)
#agent QOL params
zeroEOn = sys.argv[1]
schedOn = sys.argv[2]
saveTaskAgent = sys.argv[3]
loadTaskAgent = sys.argv[4]
provOn = sys.argv[5]
saveProvAgent = sys.argv[6]
loadProvAgent = sys.argv[7]

print("agent1 to orch!\n")
orchSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
orchSock.connect(('localhost', 7002))
orchSock.setblocking(0)
#obsSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#obsSock.connect(('localhost', 7001))
#obsSock.setblocking(0)
execSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
execSock.connect(('localhost', 7000))
execSock.setblocking(0)
execSock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
execSock2.connect(('localhost', 7000))
execSock2.setblocking(0)

curTime = time.time()
#orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff')
#todo figure out dimension of server and task inputs
#Task_dims + (num_servers * server_dims)
taskAgentStateSize = 12 + (30 * 17)
taskAgentActionSize = 30
taskAgentState = np.zeros(taskAgentStateSize)

taskAgentStateSize2 =  12 + (8 * 50) #conname,A?,B?,C?,D? UTIL MEM, UTIL CPU, exists
taskAgentActionSize2 = 50
taskAgentState2 = np.zeros(taskAgentStateSize2)

episodes = 0
episodes2 = 0
path_to_script = os.path.dirname(os.path.abspath(__file__))
mFile = os.path.join(path_to_script, "AILOGS/t1_loss.txt")
bin1 = os.path.join(path_to_script, "t1")
mFile2 = os.path.join(path_to_script, "AILOGS/t2_loss.txt")
bin2 = os.path.join(path_to_script, "t2")
taskAgent = DQNAgent(taskAgentStateSize,taskAgentActionSize,mFile,saveTaskAgent,loadTaskAgent,bin1)
taskAgent2 = DQNAgent(taskAgentStateSize2,taskAgentActionSize2,mFile2,saveTaskAgent,loadTaskAgent,bin2)

episodes3 = 0
mFile3 = os.path.join(path_to_script, "AILOGS/sched1_loss.txt")
bin3 = os.path.join(path_to_script, "sched1")
mFile4 = os.path.join(path_to_script, "AILOGS/sched2_loss.txt")
bin4 = os.path.join(path_to_script, "sched2")
mFile5 = os.path.join(path_to_script, "AILOGS/sched3_loss.txt")
bin5 = os.path.join(path_to_script, "sched3")
scheduleAgent = ScheduleNet(12,8,4,mFile3,mFile4,mFile5,saveTaskAgent,loadTaskAgent,bin3,bin4,bin5) #the dims for servs and cons are -1 since we no longer need exists


episodes4 = 0
mFile6 = os.path.join(path_to_script, "AILOGS/conProv_loss.txt")
bin6 = os.path.join(path_to_script, "prov")
conProvisioningAgent = DQNAgent(15,9,mFile6,saveProvAgent,loadProvAgent,bin6)  #A/B/C/D CPU/MEM util (x8),A/B/C/D con count (x4), timed out tasks(x1),Available CPU,Available Mem
prevServStates = {}
servs = getServers()
for serv,sObj in servs.items():
    prevServStates[serv] = np.zeros(9)
prevServActs = "none" 
prevServRewards = {}
prevServPDeprovs = {}
prevServPProvs = {}

mt = threading.Thread(target=runServer,args=())
mt.start()
#runServer()
