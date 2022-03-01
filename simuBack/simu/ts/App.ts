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
    
    router.post('/simu', async (req, res) => {
        var type = req.get('type')
        await simulate(type)

        res.json({
          message: 'done!',
          type : type
      })
    })



    this.express.use('/', router)
  }
}

export default new App().express