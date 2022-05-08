import socket
import threading
import time
import redis
import random
from signal import signal, SIGPIPE, SIG_DFL

agentThyme = True
cTaskSender = True
global execGet
execGet = False
Complete = {}
Deny = {}
Slow = {}

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

global prevCPUUsage
prevCPUUsage = {}
global prevMEMUsage
prevMEMUsage = {}

global lock
lock = threading.Lock()

r = redis.Redis(
    host='localhost',
    port=6379)

def decodeObj(obj):
    dObj = {}
    for key,val in obj.items():
        dObj[key.decode("utf-8")] = val.decode("utf-8")

    return dObj

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

def calcReqProfit(taskDat):
    profit = 0
    print("calculating profit for taskDat %s \n",taskDat)

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
    regions = r.smembers("regions")
    for reg in regions:
        regd = reg.decode("utf-8")
        rServs = r.smembers(f"{regd}_servers")
        for s in rServs:
            servObj = r.hgetall(s.decode("utf-8"))
            servs[s.decode("utf-8")] = decodeObj(servObj)

    return servs;

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
    servCosts = {}
    for serv,conDict in servCons.items():
        servCosts[serv] = 0
        servCosts[serv] += serverPassive

        for con,conObj in conDict.items():
            servCosts[serv] += conPassive

    return servCosts

#type = CPU or MEM
def getEntityUtilization(servs,mtype):
    utilizationRates = {}
    servResource = {}

    for serv,servObj in servs.items():
        print(servObj)
        servResource[serv] = float(servObj[f"serv{mtype}"]) #also servMEM

    curTasks = getTaskData()
    servUsage = {}
    for t,tObj in curTasks.items():
        if(tObj["server"] in servUsage.keys()):
            servUsage[tObj["server"]] += float(tObj[f"t{mtype}"])
        else:
            servUsage[tObj["server"]] = float(tObj[f"t{mtype}"])

    for serv,usage in servUsage.items():
        utilizationRates[serv] = float(usage)/float(servResource[serv])
    
    return utilizationRates

def getEntityDemandChange(mtype):
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

def agentTime():
    while agentThyme:
        time.sleep(15)
        displayEnvState()
        clearFinishedQueries()



def dictToTcpString(cmdVals):
    mid = cmdVals['id']
    mtype = cmdVals['type']
    ttc = cmdVals['timetocomplete']
    region = cmdVals['region']
    deps = cmdVals['deps']

    return f"id:{mid},type:{mtype},timetocomplete:{ttc},region:{region},deps:{deps}"

def handleInput(dat):
    global lock

    cmdVals = processInput(dat)
    if len(cmdVals) == 0:
        print("Empty cmdVals instance py\n")
    elif  cmdVals['cmd'] == "stask":
        #get any tasks rejected
        t = randomServConSelect()
        s = t[0]
        c = t[1]
        conInfo = decodeObj(r.hgetall(f"{c}"))
        conPort = conInfo['conPort']
        conType = conInfo['conType']
        
        taskString = dictToTcpString(cmdVals)
        with lock:
            execSock.sendall(f"cmd:sendReq,port:{conPort},contype:{conType},{taskString},server:{s},con:{c},buff:buff".encode()) #problem is here, doesn't completely send
        while not execGet:
            pass
        execGet = False
        #agentLearn()
    #print("%s\n",cmdVals)
    elif cmdVals['cmd'] == "execget":
        execGet = True
    

#todo idea: make agent time happen everytime 
HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
PORT = 7003  # Port to listen on (non-privileged ports are > 1023)
signal(SIGPIPE,SIG_DFL)  # you need this for the piping nonsense

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
                    tRep = threading.Thread(target=handleInput,args=(batch,)) #appearently the extra comma should fix the issue, try it out
                    tRep.start()
                    #handleInput(batch)
                orchSock.sendall(b'cmd:agent1Get,buff:buff')
            #conn.sendall(data)