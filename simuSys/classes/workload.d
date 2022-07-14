module simuSys.classes.workload;
import std.stdio;
import std.random;
import std.datetime.systime : SysTime, Clock;
import std.format;

class Workload
{
    Mtask[] tasks;
    string region;
    int id;
    int aChance;
    int bChance;
    int cChance;
    int dChance;
    float slacka = 1.25;
    float slackb = 1.4;
    float slackc = 1.75;
    float slackd = 2;

    this(int id,int tasks,string r,int[] typeChances)
    {
        this.id = id;

        this.aChance = typeChances[0];
        this.bChance = typeChances[1];
        this.cChance = typeChances[2];
        this.dChance = typeChances[3];

        this.generateTasks(id,tasks,r);
    }

    string generateType()
    {
        int nsecs = cast(int)Clock.currTime().fracSecs.total!"nsecs";
        auto rnd = Random(65432 * nsecs);
        auto i = uniform!"[]"(1, 100, rnd);
        writefln("%s\n",i);

        if(i <= this.aChance)
        {
            return "A";
        }
        else if(i > this.aChance && i <= (this.aChance + this.bChance))
        {
            return "B";
        }
        else if(i > (this.aChance + this.bChance) && i <= (this.aChance + this.bChance + this.cChance))
        {
            return "C";
        }
        else
        {
            return "D";
        }
    }

    float generateTaskTime(string type)
    {
        if(type == "A")
        {
            return 1 * slacka;
        }
        else if(type == "B")
        {
            return 2 * slackb;
        }
        else if(type == "C")
        {
            return 4 * slackc;
        }
        else 
        {
            return 8 * slackd;
        }
    }

    void generateTasks(int wlid,int primaryTasks,string region)
    {
        this.region = region;
        int depIndex = primaryTasks;

        for(int i = 0; i < primaryTasks; i++)
        {
            string type = this.generateType();
            float thyme = generateTaskTime(type);
            Mtask t = new Mtask(wlid,i,type,thyme,region);
            this.tasks ~= t;

            if(t.willHaveDependents())
            {
                int nsecs = cast(int)Clock.currTime().fracSecs.total!"nsecs";
                auto rnd = Random(12345 * nsecs);
                auto deps = uniform!"[]"(1, 4, rnd);

                for(int y = 0; y < deps; y++)
                {
                    string dtype = this.generateType();
                    float dthyme = generateTaskTime(dtype);
                    Mtask dt = new Mtask(wlid,(depIndex),dtype,dthyme,region);
                    dt.addDependency(i);
                    this.tasks ~= dt;
                    depIndex += 1;
                }
            }
        }
    }
}

    class Mtask
    {
        string id;
        string type;
        string region;
        float timeToComplete;
        int dependency;

        this(int wlid,int tid, string t,float time,string region)
        {
            this.id = format("%s_%s",wlid,tid);
            this.type = t;
            this.timeToComplete = time;
            this.region = region;
        }

        this(string comID,string t,float time,string region,int dep = -1)
        {
            this.id = comID;
            this.type = t;
            this.timeToComplete = time;
            this.region = region;
            this.dependency = dep;
        }

        string toTCPString()
        {
            return format("cmd:stask,id:%s,type:%s,timetocomplete:%s,region:%s,deps:%s,buff:buff",this.id,this.type,this.timeToComplete,this.region,this.dependency);
        }

        void addDependency(int depID)
        {
            this.dependency = depID;
        }

        bool willHaveDependents()
        {
            int nsecs = cast(int)Clock.currTime().fracSecs.total!"nsecs";
            auto rnd = Random(64029 * nsecs);
            auto i = uniform!"[]"(1, 3, rnd);

            if(i == 3)
            {
                return true;
            }
            else {
                return false;
            }
        }

    }