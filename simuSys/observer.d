import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;

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

void handleInput(string[string] cmdVals,Redis db)
{

    if(cmdVals["type"] == "serveradd")
    {
        string freeServQuery = format("SREM free_servers %s",
        cmdVals["servName"][1..$]);
        db.send(freeServQuery);

        string freePortQuery = format("SREM free_Ports %s",
        cmdVals["servPort"]);
        db.send(freePortQuery);

        string regionServQuery = format("SADD %s_servers %s",
        cmdVals["region"],cmdVals["servName"]);
        db.send(regionServQuery);

        string query = format("HMSET %s servPort \"%s\" servCPU \"%s\" servMEM \"%s\" region \"%s\" availableCPU \"%s\" availableMEM \"%s\"",
            cmdVals["servName"],cmdVals["servPort"],cmdVals["servCPU"],cmdVals["servMem"],cmdVals["region"],cmdVals["servCPU"],cmdVals["servMem"]);
        
        db.send(query);

        writefln("server %s saved!\n",cmdVals["servName"]);
    }
    else if(cmdVals["type"] == "serverdel")
    {
        string conQuery = format("SMEMBERS %s_containers",
        cmdVals["servName"]);
        Response containers = db.send(conQuery);

        foreach(k,v; containers.values)
        {
            string freeConPortQuery = format("HMGET %s conPort",
            v.value);
            Response conPorts = db.send(freeConPortQuery);

            string sdelConQuery = format("SREM %s_containers %s",
            cmdVals["servName"],v.value);

            string delConQuery = format("DEL %s",
            v.value);

            string freeConQuery = format("SADD free_containers %s",
            v.value[1..$]);

            db.send(sdelConQuery);
            db.send(delConQuery);
            db.send(freeConQuery);

            //free up container ports
            foreach(k1,v1; conPorts.values)
            {
                string freePortQuery1 = format("SADD free_Ports %s",
                v1.value);
                db.send(freePortQuery1);
            }
        }

        //free up server ports
        string freeServPortQuery = format("HMGET %s servPort",
        cmdVals["servName"]);
        Response servPorts = db.send(freeServPortQuery);
        foreach(k2,v2; servPorts.values)
        {
            string freePortQuery2 = format("SADD free_Ports %s",
            v2.value);
            db.send(freePortQuery2);
        }

        string getRegionQuery = format("HMGET %s region",
        cmdVals["servName"]);
        Response regions = db.send(getRegionQuery);
        foreach(k3,v3; regions.values)
        {
            string regionServQuery = format("SREM %s_servers %s",
            v3.value,cmdVals["servName"]);
            db.send(regionServQuery);
        }

        string query = format("DEL %s",
            cmdVals["servName"]);
        
        db.send(query);

        string freeServQuery = format("SADD free_servers %s",
        cmdVals["servName"][1..$]);
        db.send(freeServQuery);

        writefln("server %s deleted!\n",cmdVals["servName"]);
    }
    else if(cmdVals["type"] == "containeradd")
    {
        string freeConQuery = format("SREM free_containers %s",
        cmdVals["conName"][1..$]);
        db.send(freeConQuery);

        string freePortQuery = format("SREM free_Ports %s",
        cmdVals["conPort"]);
        db.send(freePortQuery);

        //deducts available cpu from server, need to change command to send conCPU
        int availableCPU = 0;
        string servCPUQuery = format("HMGET %s availableCPU",
        cmdVals["servName"]);
        Response cpuRes = db.send(servCPUQuery);
        foreach(cpuK,cpuV; cpuRes.values)
        {
            availableCPU = to!int(cpuV) - to!int(cmdVals["conCPU"]);
        }

        int availableMEM = 0;
        string servMEMQuery = format("HMGET %s availableMEM",
        cmdVals["servName"]);
        Response memRes = db.send(servMEMQuery);
        foreach(memK,memV; memRes.values)
        {
            availableMEM  = to!int(memV) - to!int(cmdVals["conMEM"]);
        }

        string serverEditQuery = format("HMSET %s availableCPU %s availableMEM %s",
            cmdVals["servName"],availableCPU,availableMEM);
        db.send(serverEditQuery);

        string query = format("HMSET %s conPort \"%s\" conType \"%s\" servName \"%s\" servPort \"%s\"",
            cmdVals["conName"],cmdVals["conPort"],cmdVals["conType"],cmdVals["servName"],cmdVals["servPort"]);
        
        db.send(query);

        string serverConQuery= format("SADD %s_containers %s",
        cmdVals["servName"],cmdVals["conName"]);
        db.send(serverConQuery);

        writefln("scontainer %s saved!\n",cmdVals["conName"]);
    }//todo write server edit for containerdel and edit the commands in executor
    else if(cmdVals["type"] == "containerdel")
    {
        string setDelQuery = format("SREM %s_containers %s",
        cmdVals["servName"],cmdVals["conName"]);
        db.send(setDelQuery);

        //free up container ports
        string freeConPortQuery = format("HMGET %s conPort",
        cmdVals["conName"]);
        Response conPorts = db.send(freeConPortQuery);
        foreach(k1,v1; conPorts.values)
        {
            string freePortQuery1 = format("SADD free_Ports %s",
            v1.value);
            db.send(freePortQuery1);
        }


        //adds freed resources back to server
        int availableCPU = 0;
        string servCPUQuery = format("HMGET %s availableCPU",
        cmdVals["servName"]);
        Response cpuRes = db.send(servCPUQuery);
        foreach(cpuK,cpuV; cpuRes.values)
        {
            availableCPU = to!int(cpuV) + to!int(cmdVals["conCPU"]);
        }

        int availableMEM = 0;
        string servMEMQuery = format("HMGET %s availableMEM",
        cmdVals["servName"]);
        Response memRes = db.send(servMEMQuery);
        foreach(memK,memV; memRes.values)
        {
            availableMEM  = to!int(memV) + to!int(cmdVals["conMEM"]);
        }

        string serverEditQuery = format("HMSET %s availableCPU %s availableMEM %s",
            cmdVals["servName"],availableCPU,availableMEM);
        db.send(serverEditQuery);


        string query = format("Del %s",
        cmdVals["conName"]);   
        db.send(query);

        string freeConQuery = format("SADD free_containers %s",
        cmdVals["conName"][1..$]);
        db.send(freeConQuery);

        writefln("scontainer %s deleted!\n",cmdVals["conName"]);
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

    enum MAX_CONNECTIONS = 60;
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
                char[1024] buf;
                auto datLength = reads[i].receive(buf[]);

                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength]);

                    string[] batches = to!string(buf[0..datLength]).split(",buff:buff");
                    writefln("batch: %s\n",batches);
                    foreach(string cmdLine; batches)
                    {
                        string[string] cmdVals = processInput(cmdLine);
                        //also check for empty string or \n
                        if(empty(cmdVals))
                        {
                            writefln("Empty cmdVals instance:\n");
                            continue;
                        }

                        auto t = task!handleInput(cmdVals,redis);
                        t.executeInNewThread();
                        t.workForce;
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
            sn = listener.accept();
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