"use strict";
exports.__esModule = true;
var express = require("express");
var simucommon_1 = require("simucommon");
var App = /** @class */ (function () {
    function App() {
        this.express = express();
        this.mountRoutes();
    }
    App.prototype.mountRoutes = function () {
        var router = express.Router();
        var mdb = new simucommon_1.db();
        router.post('/signup', function (req, res) {
            var uArr = new Array();
            uArr.push(req.get('id'));
            uArr.push(req.get('username'));
            uArr.push(req.get('pass'));
            uArr.push(mdb.test());
            res.json({
                message: 'Sign up success',
                fisrt: uArr[0],
                last: uArr[1],
                user: uArr[2],
                lib: uArr[3]
            });
        });
        this.express.use('/', router);
    };
    return App;
}());
exports["default"] = new App().express;
