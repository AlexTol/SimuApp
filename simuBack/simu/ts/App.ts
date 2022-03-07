import * as express from 'express'
import {simulate} from './simu'
import * as fs from 'fs'

class App {
  public express

  constructor () {
    this.express = express()
    this.mountRoutes()
  }

  private mountRoutes (): void {
    const router = express.Router()
    var type
    var MEM
    var CPU
    var Dat

    var data = fs.readFileSync('formats/format.txt','utf8')
    Dat = data.split("\n")

    type = Dat[0].split(":")[1];
    MEM = Dat[1].split(":")[1];
    CPU = Dat[2].split(":")[1];

    router.post('/simu', async (req, res) => {
        var jobMem = parseInt(req.get('jobmem'))
        var jobCPU = parseInt(req.get('jobcpu'))

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



    this.express.use('/', router)
  }
}

export default new App().express