#=====================================================================
# Design Compiler synthesis script
# 실행:  dc_shell -f syn.tcl | tee syn.log
#=====================================================================

#---------------------------------------------------------------------
# 0. 사용자 설정 (디자인마다 여기만 고치면 됨)
#---------------------------------------------------------------------
set DESIGN_NAME   pe                          ;# top module 이름
set RTL_DIR       /home/jyj/pnm-hw/pe/rtl
set RTL_FILES     [list pe.v requant.v] ;# 하위 모듈 먼저
set CLK_PORT      clk
set RST_PORT      rstn
set CLK_PERIOD    5.0                         ;

set LIB_DIR       /tools/PDK/ts65/STD/tcbn65gplus_200a/nldm/          ;
set TARGET_LIB    tcbn65gplustc.db      ;
# set DRIVE_CELL    INVX1_RVT                    ;# 입력 포트를 구동한다고 가정할 cell
# set DRIVE_PIN     Y

set REPORT_DIR    ./reports
set OUTPUT_DIR    ./outputs
file mkdir $REPORT_DIR
file mkdir $OUTPUT_DIR

#---------------------------------------------------------------------
# 1. Library setup
#---------------------------------------------------------------------
set_app_var search_path    [concat . $RTL_DIR $LIB_DIR $search_path]
set_app_var target_library [list $TARGET_LIB]          ;# 매핑에 "쓸" cell
set_app_var link_library   [concat * $TARGET_LIB]      ;# 참조를 "풀" 때 볼 곳
# (DesignWare 쓰려면: set_app_var synthetic_library dw_foundation.sldb
#                     link_library 에도 dw_foundation.sldb 추가)

define_design_lib WORK -path ./WORK                     ;# analyze 중간결과 저장 위치

#---------------------------------------------------------------------
# 2. RTL 읽기: analyze -> elaborate -> link
#---------------------------------------------------------------------
analyze -format sverilog $RTL_FILES      ;# SystemVerilog면 -format sverilog
elaborate $DESIGN_NAME                  ;# parameter override: -parameters "W=16"
current_design $DESIGN_NAME
link

check_design > $REPORT_DIR/check_design.rpt
write -format ddc -hierarchy -output $OUTPUT_DIR/${DESIGN_NAME}_elab.ddc

#---------------------------------------------------------------------
# 3. Constraints (= SDC). 별도 파일로 빼려면: source ./top.sdc
#---------------------------------------------------------------------
# 3-1. Clock
create_clock -name CLK -period $CLK_PERIOD [get_ports $CLK_PORT]
set_clock_uncertainty 0.0 [get_clocks CLK]   ;# jitter + 예상 skew 여유
set_clock_transition  0.0 [get_clocks CLK]   ;# ideal clock의 slew 가정
set_clock_latency     0.0 [get_clocks CLK]   ;# 예상 clock tree delay (선택)
set_ideal_network [get_ports $CLK_PORT]       ;# DC는 clock tree를 안 만든다

# 3-2. Reset: 고fanout net이라 DC가 buffer 넣지 않게
set_ideal_network [get_ports $RST_PORT]
set_false_path -from [get_ports $RST_PORT]    ;# async reset일 때만. sync면 지우기

# 3-3. I/O timing
set IN_PORTS [remove_from_collection [all_inputs] [get_ports [list $CLK_PORT $RST_PORT]]]
set_input_delay  [expr 0.3 * $CLK_PERIOD] -clock CLK $IN_PORTS
set_output_delay [expr 0.3 * $CLK_PERIOD] -clock CLK [all_outputs]

# 3-4. 외부 환경
# set_driving_cell -lib_cell $DRIVE_CELL -pin $DRIVE_PIN $IN_PORTS
# set_load 0.05 [all_outputs]                   ;# 단위는 library 기준 (보통 pF)

# 3-5. Design rule / optimization 목표
# set_max_fanout     16  [current_design]
# set_max_transition 0.5 [current_design]
set_max_area       0                          ;# "가능한 한 작게"

check_timing > $REPORT_DIR/check_timing.rpt   ;# unconstrained path 확인

#---------------------------------------------------------------------
# 4. Compile
#---------------------------------------------------------------------
set_fix_multiple_port_nets -all -buffer_constants   ;# netlist에 assign 안 생기게
compile_ultra -no_autoungroup                       ;# 계층 유지 (리포트 보기 편함)
# 라이선스 없으면: compile -map_effort high -area_effort high
# 결과 보고 추가 최적화: compile_ultra -incremental

#---------------------------------------------------------------------
# 5. Reports
#---------------------------------------------------------------------
report_qor                                          > $REPORT_DIR/qor.rpt
report_timing -delay_type max -max_paths 10 -nworst 1 \
              -transition_time -nets -capacitance   > $REPORT_DIR/timing_setup.rpt
report_timing -delay_type min -max_paths 10         > $REPORT_DIR/timing_hold.rpt
report_constraint -all_violators                    > $REPORT_DIR/violators.rpt
report_area -hierarchy                              > $REPORT_DIR/area.rpt
report_power -hierarchy                             > $REPORT_DIR/power.rpt
report_reference -hierarchy                         > $REPORT_DIR/reference.rpt
report_cell                                         > $REPORT_DIR/cell.rpt

#---------------------------------------------------------------------
# 6. Outputs
#---------------------------------------------------------------------
change_names -rules verilog -hierarchy
write -format verilog -hierarchy -output $OUTPUT_DIR/${DESIGN_NAME}_syn.v
write -format ddc     -hierarchy -output $OUTPUT_DIR/${DESIGN_NAME}_syn.ddc
write_sdc  $OUTPUT_DIR/${DESIGN_NAME}_syn.sdc
write_sdf  $OUTPUT_DIR/${DESIGN_NAME}_syn.sdf       ;# gate-level sim용

exit
