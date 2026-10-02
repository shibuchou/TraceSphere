#!/usr/bin/env bash
# ZSvirt MN 诊断：DB 凭据、admin 账号行、密码哈希对比
set -u
PROPS=/usr/local/zstack/apache-tomcat/webapps/zstack/WEB-INF/classes/zstack.properties

echo "== zstack-ctl file type =="
head -3 /usr/bin/zstack-ctl
echo
echo "== DB props =="
grep -iE 'DB\.(url|user|password)' "$PROPS" | head
echo
DBPW=$(grep -E '^DB.password' "$PROPS" | cut -d= -f2- | tr -d ' ')
DBUSER=$(grep -E '^DB.user' "$PROPS" | cut -d= -f2- | tr -d ' ')
echo "dbuser=$DBUSER pw_len=${#DBPW}"
echo
echo "== Account rows (uuid/name/password/type) =="
mysql -h127.0.0.1 -u"$DBUSER" -p"$DBPW" zstack -N -e 'select uuid,name,password,type from Account;' 2>&1 | head -20
echo
echo "== hashes for comparison =="
printf '%s' '${ZS_PW:?export ZS_PW}' | sha256sum
printf '%s' '${ZS_PW:?export ZS_PW}' | sha1sum
printf '%s' 'password' | sha256sum
