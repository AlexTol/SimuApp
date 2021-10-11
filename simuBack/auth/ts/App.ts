import * as express from 'express'
import * as fs from 'fs'
import {db} from 'simucommon'

class App {
  public express

  constructor () {
    this.express = express()
    this.mountRoutes()
  }

  private mountRoutes (): void {
    const router = express.Router()
   

    var data = fs.readFileSync('/opt/Simu/db.txt');
    var creds = data.toString().replace(/\r\n/g,'\n').split('\n');
    var host = creds[0].split(':')[1];
    var user = creds[1].split(':')[1];
    var pass = creds[2].split(':')[1];
    
    let mdb = new db(host,user,pass);

    router.post('/signup', async (req, res) => {
      var uArr = new Array()
      uArr['username'] = req.get('username')
      uArr['pass'] = req.get('pass')

      const result = await mdb.registerUser(uArr);

      res.json({
        message: result,
      })
    })



    this.express.use('/', router)
  }
}

export default new App().express