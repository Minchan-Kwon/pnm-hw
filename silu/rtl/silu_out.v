module silu_out (q, abs_q, htan, invalid, relu, half, y);
`include "silu_params.vh"
    input  wire signed [7:0]       q;
    input  wire        [7:0]       abs_q;
    input  wire signed [HTANW-1:0] htan;
    input  wire                    invalid, relu, half;
    output wire        [7:0]       y;

    localparam integer YW = HTANW + 10;
    wire signed [YW-1:0] prod = $signed({1'b0, abs_q}) * htan;
    wire signed [YW-1:0] acc  = prod + ($signed(q) <<< (HTANFB - 1))
                              + ($signed({{(YW-1){1'b0}}, 1'b1}) <<< (HTANFB - 1));
    wire signed [YW-1:0] ys   = acc >>> HTANFB;
    wire signed [7:0]    ylut = (ys > 127) ? 8'sd127 : (ys < -128) ? -8'sd128 : ys[7:0];

    wire signed [8:0] qh = ($signed({q[7], q}) + 9'sd1) >>> 1;
    assign y = invalid ? 8'd0 :
               relu    ? (q[7] ? 8'd0 : q) :
               half    ? qh[7:0] :
                         ylut;
endmodule