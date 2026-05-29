<?php
	// FILTERING RESULTS
	foreach ($_GET as $key => $parameter) {
		$request = $parameter != null && in_array($key, $filters) !== FALSE ? $request . "&" . $key . "=" . $parameter : $request;
		if (in_array($key, $filters) !== FALSE) $filtersValue[array_search($key, $filters)] = $parameter;
	}
	
	// EXECUTING REQUEST
	$results = restGet($request);
?>

<script>
function tableFilter(key, value){
	document.getElementById(key).value = value;
}
</script>

<form action="" method="get">
	<div class="card shadow mb-4">
		<a href="#collapseCardExample" class="d-block card-header py-3 collapsed" data-toggle="collapse" role="button" aria-expanded="false" aria-controls="collapseCardExample">
			<h6 class="m-0 font-weight-bold text-primary">Apply filters</h6>
		</a>
		<div class="collapse" id="collapseCardExample" style="">
			<div class="card-body">
			
				<?php
					foreach ($filters as $key => $parameter)
					{
						echo '
						<div class="form-inline">
							<div class="form-group mb-2">
								<input type="text" readonly class="form-control-plaintext" value="'.$parameter.'">
							</div>
							<div class="form-group mx-sm-3 mb-2">
								<input type="text" id="'.$parameter.'" class="form-control" name="'.$parameter.'" value="'.$filtersValue[$key].'">
							</div>
							
						</div>
						';
						echo "";
					}
					
				?>
				<button type="submit" class="btn btn-primary mb-2">Apply filters</button>
			</div>
		</div>
	</div>

	<div class="card shadow mb-4">
		<div class="card-header py-3">
			<h6 class="m-0 font-weight-bold text-primary">Dataset for all parks on <?php echo $env; ?> environment</h6>
		</div>
		<div class="card-body">
			<div class="table-responsive">
				<table class="table table-bordered" id="dataTable" width="100%" cellspacing="0">
					<thead>
						<tr>
							<?php
								foreach ($headers as $key => $parameter)
									echo "<th>$parameter</th>";
							?>
						</tr>
					</thead>
					<tfoot>
						<tr>
							<?php
								foreach ($headers as $key => $parameter)
									echo "<th>$parameter</th>";
							?>
						</tr>
					</tfoot>
					<tbody>
						<?php
							$membersCount = count($results[$parentField]);
							for ($index = 0; $index < $membersCount; $index++) {
								$id = explode("/", $results[$parentField][$index]['@id']);
								$id = $id[count($id) - 1];
								echo "<tr>";
								foreach ($headers as $key => $parameter)
								{
									$value = explode(".", $parameter);
									if (isset($results[$parentField][$index][$value[0]]))
									{
										
										$finalParameter = $results[$parentField][$index][$value[0]];
										for ($i = 1; $i < count($value); $i++)
										{
											$finalParameter = $finalParameter[$value[$i]];
										}
										
										if (in_array($parameter, $filters) !== FALSE)
										{
											$filtersValue[array_search($key, $filters)] = $parameter;
											$filterLink = '<button class="btn" style="padding: 0px !important" type="submit" onclick="tableFilter(\'' . $parameter . '\',\'' . $finalParameter . '\');" ><i class="fas fa-search"></i></button>
											';
										}
										if ($parameter == '@id')
											echo "<td>$id</td>";
										else
											echo "<td>$filterLink". $finalParameter ."</td>";
									}
									else
										echo "<td></td>";
								}
								echo "</tr>";
							}
						?>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</form>
<?php
	include "footer.php";
?>