#!/bin/bash

(python rarbgcli/rarbgcli.py "Brutal DooM 2013 v18 Classics-P2P" -c games -nc --order seeders --sort seeders --magnet \
    | grep "magnet:?xt=urn:btih:7afb2e8a16ba3d828b383dc15d87a5c41dd9cfa4&dn=Brutal DooM 2013 v18 Classics-P2P&tr=http%3A%2F%2Ftracker.trackerfix.com%3A80%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2710&tr=udp%3A%2F%2F9.rarbg.to%3A2710"  \
    && echo "test 1 success" \
    || (echo "test 1 fail" && exit 1)
)

(python rarbgcli/rarbgcli.py "Brutal DooM 2013 v18 Classics-P2P" -c games --order seeders --sort seeders --descending --magnet \
    | grep "magnet:?xt=urn:btih:7afb2e8a16ba3d828b383dc15d87a5c41dd9cfa4&dn=Brutal DooM 2013 v18 Classics-P2P&tr=http%3A%2F%2Ftracker.trackerfix.com%3A80%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2710&tr=udp%3A%2F%2F9.rarbg.to%3A2710"  \
    && echo "test 2 success" \
    || (echo "test 2 fail" && exit 1)
)
