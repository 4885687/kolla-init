#/bin/sh

device=$1

if [ ! -n "$device" ];then
        echo "100"
else
        iostat -cx 1 5|grep "\b$device\b"|sed -n '$p'|awk '{print $NF}'
fi


