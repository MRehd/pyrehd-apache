#!/bin/bash
#rm -rf /opt/hadoop/data/dataNode/*
chown -R hadoop:hadoop /opt/hadoop/dfs/data
chmod 755 /opt/hadoop/dfs/data
hdfs datanode