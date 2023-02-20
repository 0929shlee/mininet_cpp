n_tests=$(ls ./topology | wc -l)
for ((i=0; i<$n_tests; i++))
do
    echo sudo_password | sudo -S python ./mn_cpp.py $i
done
