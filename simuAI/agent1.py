import socket
import threading
import time
import redis
import random

cTaskSender = True

Complete["A"] = .001
Complete["B"] = .001
Complete["C"]  = .0025
Complete["D"]  = .005

Deny["A"] = .002
Deny["B"] = .002
Deny["C"] = .005
Deny["D"] = .01

Slow["A"] = .001
Slow["B"] = .001
Slow["C"] = .0025
Slow["D"] = - .001

serverPassive = .0005 
conPassive = .00005

prevCPUUsage = {}
prevMEMUsage = {}

r = redis.Redis(
    host='localhost',
    port=6379)

def randomServConSelect():
    servs = []
    tup = []
    regions = redis.smembers("regions")
    for r in regions:
        rServs = redis.smembers("{r}_servers")
        for s in rServs:
            servs.append(s)

    ser = random.choice(servs)
    tup.append(ser)
    containers = redis.smembers("{ser}_containers")
    tup.append(random.choice(containers))
    return tup
    

#todo sent commands to executor,
def processInput(dat):
    cmdVals = {}
    tuples = dat.split(",")
    for tup in tuples:
        print("%s\n",tup)
        if tup != "" and tup != "\n":
            token = tup.split(":")
            cmdVals[token[0]] = token[1]
    return cmdVals

def calcReqProfit(tasKDat):
    profit = 0
    for req,obj in taskDat.items():
        if(obj["rejected"] == 1):
            profit -= Deny[obj["type"]]
        elif(obj["timeout"] == 1):
            profit -= Slow[obj["type"]]
        elif(obj["completed"] == 1):
            profit += Complete[obj["type"]]

    return profit

def getServers():
    servs = {}
    regions = redis.smembers("regions")
    for r in regions:
        rServs = redis.smembers("{r}_servers")
        for s in rServs:
            servObj = redis.hgetall(s)
            servs[s] = servObj

    return servs;

def getContainers(servs):
    mServCons = {}
    for serv,servObj in servs.items():
        servCons = {}
        conList = redis.smembers("{serv}_containers")
        for con in conList:
            conObj = redis.hgetall(con)
            servCons[con] = conObj

        mServCons[serv] = servCons
    
    return mServCons

def getServerCost(servCons):
    servCosts = {}
    for serv,conDict in servCons.items():
        servCosts[serv] = 0
        servCosts[serv] += serverPassive

        for con,conObj in conDict.items():
            servCosts[serv] += conPassive

    return servCosts

#type = CPU or MEM
def getEntityUtilization(servs,type):
    utilizationRates = {}
    servResource = {}

    for serv,servObj in servs.items():
        servResource[serv] = servObj["serv{type}"] #also servMEM

    curTasks = getTaskData()
    servUsage = {}
    for t,tObj in curTasks.items():
        if(tObj["server"] in servUsage.keys()):
            servUsage[tObj["server"]] += tObj["t{type}"]
        else:
            servUsage[tObj["server"]] = tObj["t{type}"]

    for serv,usage in servUsage.items():
        utilizationRates[serv] = usage/servResource[serv]
    
    return utilizationRates

def getEntityDemandChange(type):
    curTasks = getTaskData()
    servDemChance = {}
    servUsage = {}
    for t,tObj in curTasks.items():
        if(tObj["server"] in servUsage.keys()):
            servUsage[tObj["server"]] += tObj["t{type}"]
        else:
            servUsage[tObj["server"]] = tObj["t{type}"]
            #for each server check diff prevCPUUsage and mem

    for serv,usage in curTasks.items():
        if(type == "CPU"):
            if(serv in prevCPUUsage,keys()):
                servDemChance[serv] = usage - prevCPUUsage[serv]
                prevCPUUsage[serv] = usage
            else:
                servDemChance[serv] = usage
                prevCPUUsage[serv] = usage
        else:
            if(serv in prevMEMUsage,keys()):
                servDemChance[serv] = usage - prevMEMUsage[serv]
                prevMEMUsage[serv] = usage
            else:
                servDemChance[serv] = usage
                prevMEMUsage[serv] = usage
        
        return servDemChance;

        

def getTaskData():
    taskDat = []

    currReqs = redis.smembers("currentRequests"))
    for req in currReqs:
        mReq = redis.hgetall(req)
        taskDat[req] = mReq

    return taskDat
    
def displayEnvState():
    taskData = getTaskData()
    profit = calcReqProfit(tasKDat)
    servs = getServers()
    servCons = getContainers(servs)
    serverCosts = getServerCost(servCons)
    cpuUtil = getEntityUtilization(servs,"CPU")
    memUtil = getEntityUtilization(servs,"MEM")
    cpuDemChange = getEntityDemandChange("CPU")
    memDemChange = getEntityDemandChange("MEM")

    print("Current EnvironmentState!\n")
    print("profit: {profit}\n")
    print("cost: per server\n")
    for serv,costs in serverCosts.items():
        print("server : {serv}     cost : {costs}\n")

    print("cpu util: per server\n")
    for serv,util in cpuUtil.items():
        print("server : {serv}     cpuUtilization : {util}")

    print("mem util: per server\n")
    for serv,util in memUtil.items():
        print("server : {serv}     memUtilization : {util}\n")

    print("cpu dem change : per server\n")
    for serv,demChange in cpuDemChange.items():
        print("server : {serv}     cpuDemandChanges : {demChange}\n")

    print("mem dem change : per server\n")
    for serv,demChange in memDemChange.items():
        print("server : {serv}     cpuDemandChanges : {demChange}\n")

def clearFinishedQueries()
    

def agentTime():
    while True:
        time.sleep(1)
        displayEnvState()



def dictToTcpString(cmdVals):
    mid = cmdVals['tid']
    mtype = cmdVals['type']
    ttc = cmdVals['timetocomplete']
    region = cmdVals['region']
    deps = cmdVals['deps']

    return "id:{mid},type:{mtype},timetocomplete:{ttc},region:{region},deps:{deps}"

def handleInput(dat):
    cmdVals = processInput(dat)
    if  cmdVals['cmd'] == "stask":
        #get any tasks rejected
        t = randomServConSelect()
        s = t[0]
        c = t[1]
        conInfo = redis.hgetall("{c}")
        conPort = conInfo['conPort']
        conType = conInfo['conType']
        
        taskString = dictToTcpString(cmdVals)
        execSock.sendall("cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{s},con:{c},buff:buff")
    #print("%s\n",cmdVals)
    


HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
PORT = 7003  # Port to listen on (non-privileged ports are > 1023)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()

    orchSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    orchSock.connect(('localhost', 7002))
    obsSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    obsSock.connect(('localhost', 7001))
    execSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    execSock.connect(('localhost', 7000))

    orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff')

    t1 = threading.Thread(target=agentTime,args=())
    t1.start()

    conn, addr = s.accept()
    with conn:
        print(f"Connected by {addr}")
        while True:
            data = conn.recv(4096)
            if not data:
                break
            else:
                strDat = data.decode("utf-8")
                print("%s\n",strDat)
                batches = strDat.split(",buff:buff")
                #get any tasks rejected
                for batch in batches:
                    tRep = threading.Thread(target=handleInput,args=(batch))
                    tRep.start()
                    #handleInput(batch)
                orchSock.sendall(b'cmd:agent1Get,buff:buff')
            #conn.sendall(data)