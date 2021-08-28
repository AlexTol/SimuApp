import * as express from 'express'

class App {
  public express

  constructor () {
    this.express = express()
    this.mountRoutes()
  }

  private mountRoutes (): void {
    const router = express.Router()

    router.post('/signup', (req, res) => {
      var uArr = new Array()
      uArr.push(req.get('id'))
      uArr.push(req.get('username'))
      uArr.push(req.get('pass'))

      res.json({
        message: 'Sign up success',
        fisrt: uArr[0],
        last: uArr[1],
        user: uArr[2],
      })
    })



    this.express.use('/', router)
  }
}

export default new App().express