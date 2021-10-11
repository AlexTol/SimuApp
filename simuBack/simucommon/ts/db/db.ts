class db {

  private pool;
  private mariadb;

  constructor (host : string, user : string, pass : string) {
    this.mariadb = require('mariadb');  

    this.pool = this.mariadb.createPool({
      host: host, 
      user: user, 
      password: pass,
      connectionLimit: 5,
      database: 'simu'
      });

  }

  public async registerUser(params : [string:string | boolean | number])
  {
    const query = `INSERT INTO users (username,pass) values ('${params['username']}','${params['pass']}')`;

    try{
      var conn = await this.pool.getConnection();
      var res = await conn.query(query);

      if(typeof res['insertId'] === 'undefined')
      {
        return 'Insert failed!';
      }

      return 'Success!'; //test this on postman
    }
    catch (err){
      throw err;
    }
    finally{
      if (conn) conn.release(); //release to pool
    }

  }

  public login()
  {

  }

  public test(){
      return "Pass! Even more!";
  }

}

export { db };