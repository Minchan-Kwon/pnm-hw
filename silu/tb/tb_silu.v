// Testbench: reads vec.hex, one 32-bit word per vector = {scale[15:0], q[7:0], y_expected[7:0]}.
// y_expected comes from the bit-accurate Python model (write_vectors), so any mismatch is an RTL bug.
`timescale 1ns/1ps
module tb_silu;
    parameter N = 1;                        // number of vectors; set with -P tb.N=<count>
    parameter LAT = 2;                      // input reg + output reg

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg        rstn = 1'b0;
    reg [7:0]  q    = 8'd0;
    reg [15:0] s    = 16'd0;
    wire [7:0] y;

    silu_a_top dut (.clk(clk), .rstn(rstn), .q_in(q), .scale_in(s), .y(y));

    reg [31:0] v [0:N-1];
    integer i, errors;

    // expected values travel through a shift register with the same latency as the DUT
    reg [7:0] exp_pipe [0:LAT-1];
    reg       vld_pipe [0:LAT-1];
    integer k;

    initial begin
        $readmemh("../vec.hex", v);
        errors = 0;
        for (k = 0; k < LAT; k = k + 1) begin exp_pipe[k] = 0; vld_pipe[k] = 0; end

        // reset check: y must be 0 while reset is held
        repeat (3) @(negedge clk);
        if (y !== 8'd0) begin $display("RESET FAIL: y=%h", y); errors = errors + 1; end
        rstn = 1'b1;

        // stream one vector per cycle
        for (i = 0; i < N + LAT; i = i + 1) begin
            @(negedge clk);
            if (vld_pipe[LAT-1] && (y !== exp_pipe[LAT-1])) begin
                errors = errors + 1;
                if (errors <= 20)
                    $display("MISMATCH vec %0d: scale=%h q=%0d  rtl=%0d  model=%0d",
                             i - LAT, v[i-LAT][31:16], $signed(v[i-LAT][15:8]),
                             $signed(y), $signed(exp_pipe[LAT-1]));
            end
            // shift the expected pipeline, then apply the next vector
            for (k = LAT-1; k > 0; k = k - 1) begin
                exp_pipe[k] = exp_pipe[k-1]; vld_pipe[k] = vld_pipe[k-1];
            end
            if (i < N) begin
                s = v[i][31:16]; q = v[i][15:8];
                exp_pipe[0] = v[i][7:0]; vld_pipe[0] = 1'b1;
            end else begin
                vld_pipe[0] = 1'b0;
            end
        end
        $display("RESULT: %0d vectors, %0d errors -> %s", N, errors, errors ? "FAIL" : "PASS");
        $finish;
    end
endmodule