#!/bin/bash
if [ ! -d "/hadoop/dfs/name/current" ]; then
    echo "Formatting NameNode..."
    echo Y | hdfs namenode -format
fi
hdfs namenode