import * as express from 'express'
import {simulate} from './simu'
import * as fs from 'fs'
import path = require('path')

class App {
  public express

  constructor () {
    this.express = express()
    this.mountRoutes()
  }

  private mountRoutes (): void {
    const router = express.Router()
    var type
    var totMEM
    var MEM
    var totCPU
    var CPU
    var Dat

    var data = fs.readFileSync(path.resolve(__dirname, '../formats/format.txt'),'utf8')
    Dat = data.split("\n")

    type = Dat[0].split(":")[1];
    totMEM = parseFloat(Dat[1].split(":")[1]);
    MEM = parseFloat(Dat[1].split(":")[1]);
    totCPU = parseFloat(Dat[2].split(":")[1]);
    CPU = parseFloat(Dat[2].split(":")[1]);

    router.post('/simu', async (req, res) => {
        var jobMem = parseFloat(req.get('jobmem'))
        var jobCPU = parseFloat(req.get('jobcpu'))

        if(jobMem > MEM)
        {
          res.json({
              message: 'FAIL',
              reason : 'MEM'
          })
          return
        }
        else if(jobCPU > CPU)
        {
          res.json({
            message: 'FAIL',
            reason : 'CPU'
          })
          return
        }

        MEM = MEM - jobMem
        CPU = CPU - jobCPU
        await simulate(type)
        MEM = MEM + jobMem
        CPU = CPU + jobCPU

        res.json({
          message: 'done!',
          type : type,
          mem : MEM,
          cpu : CPU
      })
    })

    router.post('/simuUtil', async (req, res) => {
      var memUtil = MEM/totMEM
      var cpuUtil = CPU/totCPU

      res.json({
        message: 'done!',
        mUTIL : memUtil,
        cUtil : cpuUtil,
    })
  })

    this.express.use('/', router)
  }
}

export default new App().express