#!/bin/sh
# 늑대왕 손 튜닝 통계 (.NET 하네스): sh QaTools~/wk_stats.sh [n]
cd "$(dirname "$0")/harness" && dotnet build -c Release -v q 2>&1 | grep -E " error " | sort -u | head -5
D="$(cd ../../Assets/QA/Data/Resources/QaData && pwd -W)"
H=$(ls bin/Release/*/Harness.dll)
for c in warrior mage archer; do dotnet $H stats "$D" $c forest_wolf_king ${1:-300}; done
