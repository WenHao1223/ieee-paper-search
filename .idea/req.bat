curl --url 'https://ieeexplore.ieee.org/rest/search' \
  -H 'content-type: application/json' \
  -H 'referer: https://ieeexplore.ieee.org/search/searchresult.jsp' \
  -H 'user-agent: hi' \
  --data-raw '{"queryText":"ai"}'