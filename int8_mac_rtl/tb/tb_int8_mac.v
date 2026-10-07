`timescale 1ns/1ps

module tb_int8_mac;

    reg clk;
    reg rst_n;
    reg signed [7:0] a;
    reg signed [7:0] b;

    wire signed [31:0] acc;

    int8_mac dut (
        .clk(clk),
        .rst_n(rst_n),
        .a(a),
        .b(b),
        .acc(acc)
    );

initial begin
    clk = 1'b0;
end

always #5 clk = ~clk;

initial begin
    rst_n = 1'b0;
    a = 8'sd0;
    b = 8'sd0;

    #12;
    rst_n = 1'b1;
    a = 8'sd2;
    b = 8'sd3;

#30;
$display("양수 누산: acc = %0d", acc);

a = -8'sd2;
b = 8'sd3;

#20;
$display("음수 누산: acc = %0d", acc);
$finish;
end

endmodule