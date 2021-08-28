import app from './App'


app.listen(8000, (err) => {
  if (err) {
    return console.log(err)
  }

  return console.log(`server is listening on 8000`)
})