import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.datetime.systime : SysTime, Clock;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;
import simuSys.classes.workload;
import std.random;
import core.time;
import core.thread.osthread;

shared bool exFullyConnected = false;
shared bool agent1FullyConnected = false;
shared bool shutDownComsExecuted = false;
shared bool agent1Get = false;
shared Socket exec;
shared Socket obs;
shared Socket agent1;

string[string] processInput(string input)
{
    string[string] cmdVals;

    string[] tuples = input.split(",");
    foreach (string tuple; tuples)
    {
        if(tuple != "" && tuple != "\n")
        {
            string[] token = tuple.split(":");
            cmdVals[token[0]] = token[1];
        }
    }

    return cmdVals;
}

void parallelSocketSend(Socket sock,string com)
{
    sock.send(com);
}

void startupServers()
{
    string[] initServComs;
    Socket mExec = cast(Socket)exec;

    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:NA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:SA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:EU,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:AF,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:AS,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:100,servMEM:100,region:AU,buff:buff");

    foreach(string com; initServComs)
    {
        for(int i = 0; i < 1; i++)
        {
            mExec.send(com);
        }
    }

}

void startupCons()
{
    for(int i = 1; i <= 6; i++)
    {
        string containerCom1 = format("cmd:createCon,servName:s%s,conType:A,buff:buff",i);
        string containerCom2 = format("cmd:createCon,servName:s%s,conType:B,buff:buff",i);
        string containerCom3 = format("cmd:createCon,servName:s%s,conType:C,buff:buff",i);
        string containerCom4 = format("cmd:createCon,servName:s%s,conType:D,buff:buff",i);

        Socket mExec = cast(Socket)exec;

        mExec.send(containerCom1);
        mExec.send(containerCom2);
        mExec.send(containerCom3);
        mExec.send(containerCom4);
    }
}

void waitSignal(shared ref bool sig)
{
    while(!sig)
    {

    }
}

void initEnvironment(Redis db)
{
    string basePath = "/home/dev/Projects/thesis/SimuApp/simuSys";
    string aiPath = "/home/dev/Projects/thesis/SimuApp/simuAI";
    string cmd1 = format("%s/executor",basePath);
    string cmd2 = format("%s/observer",basePath);
    string agent1Path = format("%s/agent1.py",aiPath);

    spawnProcess(cmd1);
    spawnProcess(cmd2);
    spawnProcess(["python",agent1Path]);

    string regionQuery = format("SADD regions NA SA EU AF AS AU");
    db.send(regionQuery);

    bool connect1 = false;
    while(!connect1)
    {
        try
        {
            auto rexec = (new TcpSocket(new InternetAddress("127.0.0.1", 7000)));
            //rexec.blocking = false;
            exec = cast(shared Socket) rexec;
            connect1 = true;
        }
        catch(SocketException e)
        {
            connect1 = false;
        }
    }

    bool connect2 = false;
    while(!connect2)
    {
        try
        {
            auto robs = (new TcpSocket(new InternetAddress("127.0.0.1", 7001)));
            //robs.blocking = false;
            obs = cast(shared Socket) robs;
            connect2 = true;
        }
        catch(SocketException e)
        {
            connect2 = false;
        }
    }

    bool connect3 = false;
    while(!connect3)
    {
        try
        {
            auto ragent1 = (new TcpSocket(new InternetAddress("127.0.0.1", 7003)));
            //ragent1.blocking = false;
            agent1 = cast(shared Socket) ragent1;
            connect3 = true;
        }
        catch(SocketException e)
        {
            connect3 = false;
        }
    }
    
    string execLinkCommand = format("cmd:connect,buff:buff");
    Socket mExec = cast(Socket)exec;
    mExec.send(execLinkCommand);
    //wait for socks to be fully connected
    waitSignal(exFullyConnected);

    string agent1LinkCommand = format("cmd:connect,buff:buff");
    Socket mAgent1 = cast(Socket)agent1;
    mAgent1.send(agent1LinkCommand);

    waitSignal(agent1FullyConnected);
    
    writefln("Executor and Observer are online! \n");

    startupServers();

    int AUServs = 0;
    while(AUServs < 1)
    {
        auto aus = db.send("SMEMBERS","AU_servers");
        foreach(k,v; aus)
        {
            AUServs += 1;
        }
    }

    writefln("All servers are up! \n");

    startupCons();

    int s6Cons = 0;
    while(s6Cons < 4)
    {
        auto cons = db.send("SMEMBERS","s6_containers");
        foreach(k,v; cons)
        {
            s6Cons += 1;
        }
    }

    writefln("All containers are up! \n");
}

void shutDownEnvironment(Redis db)
{
    //todo find better way to kill python socket (probably send signal), also make it so it catches the socket not available error (on obs or exec)
    string totalShutDownCom = "cmd:totalShut,buff:buff";
    Socket mExec = cast(Socket) exec;
    mExec.send(totalShutDownCom);

    while(!shutDownComsExecuted)
    {

    }

    string flushQuery = "flushall";
    db.send(flushQuery);

    string killEXECcom = "fuser -k 7000/tcp";
    string killOBScom = "fuser -k 7001/tcp";
    string killAgent1Com = "fuser -k 7003/tcp";

    executeShell(killEXECcom);
    executeShell(killOBScom);
    executeShell(killAgent1Com);

    writefln("All processes are off!\n",);
}

string generateRegion(int[] regionChances)
{
        int nsecs = cast(int)Clock.currTime().fracSecs.total!"nsecs";
        auto rnd = Random(23456 * nsecs);
        auto i = uniform!"[]"(1, 100, rnd);

        if(i <= regionChances[0])
        {
            return "NA";
        }
        else if(i <= (regionChances[1] + regionChances[0]) && i > regionChances[0])
        {
            return "SA";
        }
        else if(i <= (regionChances[2] + regionChances[1] + regionChances[0]) && i > (regionChances[1] + regionChances[0]))
        {
            return "EU";
        }
        else if(i <= (regionChances[3] + regionChances[2] + regionChances[1] + regionChances[0]) && i > (regionChances[2] + regionChances[1] + regionChances[0]))
        {
            return "AF";
        }
        else if(i <= (regionChances[4] + regionChances[3] + regionChances[2] + regionChances[1] + regionChances[0]) && i > (regionChances[3] + regionChances[2] + regionChances[1] + regionChances[0]))
        {
            return "AS";
        }
        else 
        {
            return "AU";    
        }
}

void generateTasks()
{
    //todo send this to python agent and also make sure to save tasks to redis
    int[] typechances = [40,20,20,20];
    int[] regionChances = [50,5,25,5,10,5];
    int wlid = 1;
    Socket mAgent1 = cast(Socket) agent1;

    while(true)
    {
        string region = generateRegion(regionChances);

        int nsecs = cast(int)Clock.currTime().fracSecs.total!"nsecs";
        auto rnd = Random(13579 * nsecs);
        auto tasks = uniform!"[]"(1, 100, rnd);

        Workload wl = new Workload(wlid,tasks,region,typechances);
        foreach( task; wl.tasks)
        {
            string cmd = format("%s",task.toTCPString());
            //writefln("%s\n",task.toTCPString());

            mAgent1.send(cmd);
            waitSignal(agent1Get);
            agent1Get = false;
        }

        Thread.sleep(dur!("seconds")( 120)); //todo play with this

        wlid += 1;
    }

    //generate chances for regions and create and display workloads.
}

void handleInput(string[string] cmdVals,Redis db)
{
    if(cmdVals["cmd"] == "initEnv")
    {
        initEnvironment(db);
    }
    else if(cmdVals["cmd"] == "shutDownEnv")
    {
        shutDownEnvironment(db);
    }
    else if(cmdVals["cmd"] == "exFullyConnected")
    {
        exFullyConnected = true;
        writefln("%s\n",exFullyConnected);
    }
    else if(cmdVals["cmd"] == "agent1FullyConnected")
    {
        agent1FullyConnected = true;
    }
    else if(cmdVals["cmd"] == "shutDownComsExecuted")
    {
        shutDownComsExecuted = true;
        writefln("%s\n",shutDownComsExecuted);
    }
    else if(cmdVals["cmd"] == "generateTasks")
    {
        generateTasks();
    }
    else if(cmdVals["cmd"] == "agent1Get")
    {
        agent1Get = true;
    }
}

void main(string[] args)
{
    ushort port;

    if (args.length >= 2)
        port = to!ushort(args[1]);
    else
        port = 7002;

    auto listener = new TcpSocket();
    assert(listener.isAlive);
    listener.blocking = false;
    listener.bind(new InternetAddress(port));
    listener.listen(1000);
    writefln("Listening on port %d.", port);

    enum MAX_CONNECTIONS = 600;
    // Room for listener.
    auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
    Socket[] reads;

    auto redis = new Redis("localhost", 6379);
    while (true)
    {
        //auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
        writefln("orch here0 \n");
        socketSet.add(listener);
        long sel;

        foreach (sock; reads)
            socketSet.add(sock);

        try
        {
            sel = Socket.select(socketSet, null, null);
        }
        catch (SocketException e)
        {
            socketSet.reset();
            continue;            
        }

        for (size_t i = 0; i < reads.length; i++)
        {
            writefln("Socket blocking %s \n",reads[i].blocking);
            if (socketSet.isSet(reads[i]))
            {
                //reads[i].blocking = false;
                //writefln("orch here1 \n");
                //writefln("orch reads: %s \n",reads.length);
                //writefln("adress of current req socket: %s \n",reads[i].remoteAddress());
                //writefln("sel was %s \n",sel);
                char[4096] buf;

                long datLength;
                if(sel != -1)
                {
                     datLength = reads[i].receive(buf[]);
                }
                else
                {
                    buf = "cmd:blank,buff:buff";
                    datLength = buf.length;
                }
                
                //writefln("orch here1.5 \n");
                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength]);
                    string[string] cmdVals = processInput(to!string(buf[0..datLength]));
                
                    auto t = task!handleInput(cmdVals,redis);
                    t.executeInNewThread();
                    //writefln("orch pass1 \n");
                    //t.workForce;

                    continue;
                }
                else
                {
                    try
                    {
                        // if the connection closed due to an error, remoteAddress() could fail
                        writefln("Connection from %s closed.", reads[i].remoteAddress().toString());
                    }
                    catch (SocketException)
                    {
                        writeln("Connection closed.");
                    }
                }
                // release socket resources now
                reads[i].close();

                reads = reads.remove(i);
                // i will be incremented by the for, we don't want it to be.
                i--;
                //writefln("orch pass2 \n");
            }
            //writefln("orch pass3 \n");
        }

        if (socketSet.isSet(listener))        // connection request
        {
            writefln("orch here2 \n");
            Socket sn = null;
            scope (failure)
            {
                writefln("Error accepting");

                /**
                if (sn)
                    sn.close();*/
            }

            try
            {
                sn = listener.accept();
            }
            catch(SocketException e)
            {
                //writefln("%s\n",e);
                continue;
            }

            //sn = listener.accept();
            

            assert(sn.isAlive);
            assert(listener.isAlive);

            if (reads.length < MAX_CONNECTIONS)
            {
                writefln("Orch : Connection from %s established.", sn.remoteAddress().toString());
                reads ~= sn; //takes in new data
                writefln("\tTotal connections: %d", reads.length);
            }
            else
            {
                writefln("Rejected connection from %s; too many connections.", sn.remoteAddress().toString());
                sn.close();
                assert(!sn.isAlive);
                assert(listener.isAlive);
            }

        }

        socketSet.reset();
    }
}