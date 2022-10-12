import std.file;
import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;

Socket[string] socks;

Response execRedis(Redis db,string query)
{
    synchronized
    {
        return db.send(query);
    }
}

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

void handleInput(string[string] cmdVals,Redis db,Socket[string] socks)
{

    if(cmdVals["type"] == "serveradd")
    {
        string freeServQuery = format("SREM free_servers %s",
        cmdVals["servName"][1..$]);
        execRedis(db,freeServQuery);

        string freePortQuery = format("SREM free_Ports %s",
        cmdVals["servPort"]);
        execRedis(db,freePortQuery);

        string query = format("HMSET %s servPort \"%s\" servCPU \"%s\" servMEM \"%s\" region \"%s\" availableCPU \"%s\" availableMEM \"%s\"",
            cmdVals["servName"],cmdVals["servPort"],cmdVals["servCPU"],cmdVals["servMem"],cmdVals["region"],cmdVals["servCPU"],cmdVals["servMem"]);
        
        execRedis(db,query);

        string regionServQuery = format("SADD %s_servers %s",
        cmdVals["region"],cmdVals["servName"]);
        execRedis(db,regionServQuery);

        writefln("server %s saved!\n",cmdVals["servName"]);

        synchronized 
        {
            socks["exec"].send("cmd:sAddConfirmed,buff:buff");
            writefln("sent to agent1!!!!!\n");
        }
    }
    else if(cmdVals["type"] == "serverdel")
    {
        string conQuery = format("SMEMBERS %s_containers",
        cmdVals["servName"]);
        Response containers = execRedis(db,conQuery);

        foreach(k,v; containers.values)
        {
            string freeConPortQuery = format("HMGET %s conPort",
            v.value);
            Response conPorts = execRedis(db,freeConPortQuery);

            string sdelConQuery = format("SREM %s_containers %s",
            cmdVals["servName"],v.value);

            string delConQuery = format("DEL %s",
            v.value);

            string freeConQuery = format("SADD free_containers %s",
            v.value[1..$]);

            execRedis(db,sdelConQuery);
            execRedis(db,delConQuery);
            execRedis(db,freeConQuery);

            //free up container ports
            foreach(k1,v1; conPorts.values)
            {
                string freePortQuery1 = format("SADD free_Ports %s",
                v1.value);
                execRedis(db,freePortQuery1);
            }
        }

        //free up server ports
        string freeServPortQuery = format("HMGET %s servPort",
        cmdVals["servName"]);
        Response servPorts = execRedis(db,freeServPortQuery);
        foreach(k2,v2; servPorts.values)
        {
            string freePortQuery2 = format("SADD free_Ports %s",
            v2.value);
            execRedis(db,freePortQuery2);
        }

        string getRegionQuery = format("HMGET %s region",
        cmdVals["servName"]);
        Response regions = execRedis(db,getRegionQuery);
        foreach(k3,v3; regions.values)
        {
            string regionServQuery = format("SREM %s_servers %s",
            v3.value,cmdVals["servName"]);
            execRedis(db,regionServQuery);
        }

        string query = format("DEL %s",
            cmdVals["servName"]);
        
        execRedis(db,query);

        string freeServQuery = format("SADD free_servers %s",
        cmdVals["servName"][1..$]);
        execRedis(db,freeServQuery);

        writefln("server %s deleted!\n",cmdVals["servName"]);

        synchronized 
        {
            socks["exec"].send("cmd:sDelConfirmed,buff:buff");
            writefln("sent to agent1!!!!!\n");
        }
    }
    else if(cmdVals["type"] == "containeradd")
    {
        synchronized 
        {
            string freeConQuery = format("SREM free_containers %s",
            cmdVals["conName"][1..$]);
            writefln("freeconquery : %s\n",freeConQuery);
            execRedis(db,freeConQuery);

            string freePortQuery = format("SREM free_Ports %s",
            cmdVals["conPort"]);
            writefln("freeportquery : %s\n",freePortQuery);
            execRedis(db,freePortQuery);

            //deducts available cpu from server, need to change command to send conCPU
            int availableCPU = 0;
            string servCPUQuery = format("HMGET %s availableCPU",
            cmdVals["servName"]);
            Response cpuRes = execRedis(db,servCPUQuery);
            foreach(cpuK,cpuV; cpuRes.values)
            {
                availableCPU = to!int(cpuV) - to!int(cmdVals["conCPU"]);
            }

            float availableMEM = 0;
            string servMEMQuery = format("HMGET %s availableMEM",
            cmdVals["servName"]);
            Response memRes = execRedis(db,servMEMQuery);
            foreach(memK,memV; memRes.values)
            {
                availableMEM  = to!float(to!string(memV)) - to!float(cmdVals["conMEM"]);
            }

            string serverEditQuery = format("HMSET %s availableCPU %s availableMEM %s",
                cmdVals["servName"],availableCPU,availableMEM);
            execRedis(db,serverEditQuery);

            string query = format("HMSET %s conPort \"%s\" conType \"%s\" servName \"%s\" servPort \"%s\" conCPU \"%s\" conMEM \"%s\"",
                cmdVals["conName"],cmdVals["conPort"],cmdVals["conType"],cmdVals["servName"],cmdVals["servPort"],cmdVals["conCPU"],cmdVals["conMEM"]);

            execRedis(db,query);

            string serverConQuery= format("SADD %s_containers %s",
            cmdVals["servName"],cmdVals["conName"]);
            execRedis(db,serverConQuery);

            writefln("scontainer %s saved!\n",cmdVals["conName"]);

            if(cmdVals["agent"] != "no")
            {
                socks["agent1"].send("cmd:cAddConfirmed,buff:buff");
            }
            socks["exec"].send("cmd:cAddConfirmed,buff:buff");
            writefln("sent to agent1!!!!!\n");
        }

    }//todo write server edit for containerdel and edit the commands in executor
    else if(cmdVals["type"] == "containerdel")
    {
        synchronized 
        {
            string setDelQuery = format("SREM %s_containers %s", //todo maybe this srem is funky...
            cmdVals["servName"],cmdVals["conName"]);
            writefln("setDelQuery %s\n",setDelQuery);
            execRedis(db,setDelQuery);

            //free up container ports
            string freeConPortQuery = format("HMGET %s conPort",
            cmdVals["conName"]);
            Response conPorts = execRedis(db,freeConPortQuery);
            foreach(k1,v1; conPorts.values)
            {
                string freePortQuery1 = format("SADD free_Ports %s",
                v1.value);
                execRedis(db,freePortQuery1);
            }


            //adds freed resources back to server
            int availableCPU = 0;
            string servCPUQuery = format("HMGET %s availableCPU",
            cmdVals["servName"]);
            Response cpuRes = execRedis(db,servCPUQuery);
            foreach(cpuK,cpuV; cpuRes.values)
            {
                availableCPU = to!int(cpuV) + to!int(cmdVals["conCPU"]);
            }

            float availableMEM = 0;
            string servMEMQuery = format("HMGET %s availableMEM",
            cmdVals["servName"]);
            Response memRes = execRedis(db,servMEMQuery);
            foreach(memK,memV; memRes.values)
            {
                availableMEM  = to!float(to!string(memV)) + to!float(cmdVals["conMEM"]);
            }

            string serverEditQuery = format("HMSET %s availableCPU %s availableMEM %s",
                cmdVals["servName"],availableCPU,availableMEM);
            execRedis(db,serverEditQuery);


            string query = format("Del %s",
            cmdVals["conName"]);   
            execRedis(db,query);

            string freeConQuery = format("SADD free_containers %s",
            cmdVals["conName"][1..$]);
            writefln("freeconquery (add): %s\n",freeConQuery);
            execRedis(db,freeConQuery);

            writefln("scontainer %s deleted!\n",cmdVals["conName"]);


            socks["agent1"].send("cmd:cDelConfirmed,buff:buff");
            socks["exec"].send("cmd:cDelConfirmed,buff:buff");
            writefln("sent to agent1!!!!!\n");
        }
    }
    else if(cmdVals["type"] == "reqStatus")
    {
        //todo log
            writefln("saving request data!!!\n");
            string setQuery = format("SADD currentRequests %s",cmdVals["tid"]);
            execRedis(db,setQuery);

            string reqQuery = format("HMSET %s type %s region %s completed %s elapsed %s timeout %s rejected %s server %s con %s tCPU %s tMEM %s",
            cmdVals["tid"],cmdVals["tType"],cmdVals["region"],cmdVals["completed"],cmdVals["elapsed"],cmdVals["timeout"],cmdVals["rejected"],cmdVals["server"],cmdVals["con"],cmdVals["tCPU"],cmdVals["tMEM"]);
            writefln("hmset query %s\n",reqQuery);
            execRedis(db,reqQuery);

            synchronized
            {
                socks["exec"].send("cmd:reqConfirmed,buff:buff");
            }
    }
    else {
        writefln("no match! %s \n",cmdVals);
    }

}

void main(string[] args)
{
    ushort port;

    if (args.length >= 2)
        port = to!ushort(args[1]);
    else
        port = 7001;

    auto listener = new TcpSocket();
    assert(listener.isAlive);
    listener.blocking = false;
    listener.bind(new InternetAddress(port));
    listener.listen(10);
    writefln("Listening on port %d.", port);

    enum MAX_CONNECTIONS = 1200;
    // Room for listener.
    auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
    Socket[] reads;

    auto redis = new Redis("localhost", 6379);
    while (true)
    {
        socketSet.add(listener);

        foreach (sock; reads)
            socketSet.add(sock);

        Socket.select(socketSet, null, null);

        for (size_t i = 0; i < reads.length; i++)
        {
            if (socketSet.isSet(reads[i]))
            {
                char[4096] buf;
                auto datLength = reads[i].receive(buf[]);

                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength]);

                    string[] batches = to!string(buf[0..datLength]).split(",buff:buff");
                    writefln("observer batches: %s\n",batches);
                    foreach(string cmdLine; batches)
                    {
                        writefln("observer batch: %s\n",cmdLine);
                        string[string] cmdVals = processInput(cmdLine);
                        //also check for empty string or \n
                        if(empty(cmdVals))
                        {
                            writefln("Empty cmdVals instance:\n");
                            continue;
                        }
                        else if(cmdVals["type"] == "connect")
                        {
                            socks["agent1"] = new TcpSocket(new InternetAddress("127.0.0.1", 7003));
                            socks["orch"] = new TcpSocket(new InternetAddress("127.0.0.1", 7002));
                            socks["exec"] = new TcpSocket(new InternetAddress("127.0.0.1", 7000));

                            socks["orch"].send("cmd:obsFullyConnected,buff:buff");
                        }
                        else
                        {
                            auto t = task!handleInput(cmdVals,redis,socks);
                            t.executeInNewThread();
                            t.workForce;
                        }
                    }

                    continue;
                }

                // release socket resources now
                reads[i].close();

                reads = reads.remove(i);
                // i will be incremented by the for, we don't want it to be.
                i--;
            }
        }

        if (socketSet.isSet(listener))        // connection request
        {
            Socket sn = null;
            scope (failure)
            {
                writefln("Error accepting");

                if (sn)
                    sn.close();
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
            
            assert(sn.isAlive);
            assert(listener.isAlive);

            if (reads.length < MAX_CONNECTIONS)
            {
                writefln("Connection from %s established.", sn.remoteAddress().toString());
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