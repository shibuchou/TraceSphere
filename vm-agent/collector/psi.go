package collector

import (
	"bufio"
	"os"
	"strconv"
	"strings"
)

// PSI 为 /proc/pressure/<resource> 的解析结果。
type PSI struct {
	SomeAvg10  float64 `json:"some_avg10"`
	SomeTotal  uint64  `json:"some_total_us"`
	FullAvg10  float64 `json:"full_avg10"`
	FullTotal  uint64  `json:"full_total_us"`
}

// ReadPSI 读取指定资源（cpu / memory / io）的压力指标。
func ReadPSI(resource string) (PSI, error) {
	f, err := os.Open("/proc/pressure/" + resource)
	if err != nil {
		return PSI{}, err
	}
	defer f.Close()

	var p PSI
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		switch {
		case strings.HasPrefix(line, "some "):
			parsePSILine(strings.TrimPrefix(line, "some "), &p.SomeAvg10, &p.SomeTotal)
		case strings.HasPrefix(line, "full "):
			parsePSILine(strings.TrimPrefix(line, "full "), &p.FullAvg10, &p.FullTotal)
		}
	}
	return p, sc.Err()
}

func parsePSILine(s string, avg10 *float64, total *uint64) {
	for _, kv := range strings.Fields(s) {
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) != 2 {
			continue
		}
		switch parts[0] {
		case "avg10":
			if v, err := strconv.ParseFloat(parts[1], 64); err == nil {
				*avg10 = v
			}
		case "total":
			if v, err := strconv.ParseUint(parts[1], 10, 64); err == nil {
				*total = v
			}
		}
	}
}
